"""Real Matching API integration test (PostgreSQL + Core models).

Run from the costpilot-backend project root:
    uv run pytest tests/test_matching_api.py -v -s

Requires a running, populated CostPilot PostgreSQL instance and the local
embedding / reranking model paths configured in MODELS_CONFIG_PATH.
"""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app

# Synthetic GAEB file: no company or customer tender data.
SAMPLE_TENDER = """\
<?xml version="1.0" encoding="UTF-8"?>
<GAEB xmlns="http://www.gaeb.de/GAEB_DA_XML/200407">
  <Award>
    <BoQ>
      <BoQInfo>
        <BoQBkdn><Type>BoQLevel</Type><Length>2</Length></BoQBkdn>
        <BoQBkdn><Type>Item</Type><Length>3</Length></BoQBkdn>
      </BoQInfo>
      <BoQBody>
        <BoQCtgy RNoPart="1">
          <BoQCatInfo><LblTx>Betonarbeiten</LblTx></BoQCatInfo>
          <BoQBody>
            <Itemlist>
              <Item RNoPart="1">
                <Qty>15.50</Qty><QU>m3</QU>
                <Description><CompleteText>
                  <OutlineText>Stahlbeton C30/37</OutlineText>
                  <DetailTxt>Transportbeton fuer Fundamente, Festigkeitsklasse C30/37.</DetailTxt>
                </CompleteText></Description>
              </Item>
              <Item RNoPart="2">
                <Qty>5.25</Qty><QU>t</QU>
                <Description><CompleteText>
                  <OutlineText>Betonstahl B500B</OutlineText>
                  <DetailTxt>Gerippter Bewehrungsstahl fuer Stahlbetonbauteile.</DetailTxt>
                </CompleteText></Description>
              </Item>
            </Itemlist>
          </BoQBody>
        </BoQCtgy>
      </BoQBody>
    </BoQ>
  </Award>
</GAEB>
"""


def test_matching_api_end_to_end() -> None:
    """Project -> Tender upload -> Matching -> Stored results; cleans up all test data."""
    app = create_app()
    project_name = f"TEST_MATCHING_{uuid4().hex}"

    with TestClient(app) as client:
        pool = app.state.db_pool
        try:
            # Catalog data already exists; the test must not modify it.
            with pool.connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM commodity_search),
                        (SELECT COUNT(*) FROM commodity_embeddings);
                    """
                )
                counts = cursor.fetchone()
                assert counts is not None
                assert counts[0] > 0, (
                    "commodity_search is empty; build the search projection first."
                )
                assert counts[1] > 0, (
                    "commodity_embeddings is empty; build embeddings first."
                )

            # 1. Create project.
            response = client.post("/projects", json={"name": project_name})
            assert response.status_code == 201, response.text
            project_id = response.json()["id"]

            # 2. Upload and parse a synthetic Tender.
            response = client.post(
                f"/projects/{project_id}/tenders",
                files={
                    "file": (
                        "matching_demo.x83",
                        SAMPLE_TENDER.encode("utf-8"),
                        "application/xml",
                    )
                },
            )
            assert response.status_code == 201, response.text
            tender_id = response.json()["id"]

            response = client.get(f"/projects/{project_id}/tenders/{tender_id}/items")
            assert response.status_code == 200, response.text
            uploaded_items = response.json()
            assert len(uploaded_items) == 2
            expected_position_ids = {item["position_id"] for item in uploaded_items}

            # 3. No match results have been stored yet.
            base_url = f"/projects/{project_id}/tenders/{tender_id}"
            response = client.get(f"{base_url}/matches")
            assert response.status_code == 200, response.text
            assert response.json() == []

            # 4. Real matching: BM25 + pgvector + Core RRF + Core Reranker.
            response = client.post(f"{base_url}/match")
            assert response.status_code == 200, response.text

            payload = response.json()
            assert payload["project_id"] == project_id
            assert payload["tender_id"] == tender_id
            results = payload["results"]
            assert len(results) == len(uploaded_items)
            assert {item["position_id"] for item in results} == expected_position_ids

            for item in results:
                assert item["status"] in {"REVIEW_REQUIRED", "UNMATCHED"}
                candidates = item["candidates"]
                assert isinstance(candidates, list)
                assert all(
                    candidates[i]["score"] >= candidates[i + 1]["score"]
                    for i in range(len(candidates) - 1)
                )
                if candidates:
                    assert item["status"] == "REVIEW_REQUIRED"
                    assert item["commodity_id"] == candidates[0]["commodity"]["id"]
                else:
                    assert item["status"] == "UNMATCHED"
                    assert item["commodity_id"] is None

                print(
                    f"OZ={item['oz']} | {item['short_text']} | "
                    f"{item['status']} | commodity_id={item['commodity_id']}"
                )
                for candidate in candidates:
                    print(
                        f"  {candidate['commodity']['code']} "
                        f"score={candidate['score']:.4f} "
                        f"{candidate['commodity']['description']}"
                    )

            # Query embeddings were required for this test; a populated catalog
            # should return at least one candidate for these example positions.
            assert any(item["candidates"] for item in results), (
                "Matching completed but returned no candidates."
            )

            # 5. Check that the database persisted the results.
            response = client.get(f"{base_url}/matches")
            assert response.status_code == 200, response.text
            stored = response.json()
            assert len(stored) == len(results)

            stored_by_id = {row["position_id"]: row for row in stored}
            for item in results:
                row = stored_by_id[item["position_id"]]
                assert row["status"] == item["status"]
                assert row["commodity_id"] == item["commodity_id"]
                # Stored score can be null when the reranker emits raw logits.

            # 6. Missing Tender: both endpoints should return 404.
            missing_url = f"/projects/{project_id}/tenders/999999999999"
            assert client.post(f"{missing_url}/match").status_code == 404
            assert client.get(f"{missing_url}/matches").status_code == 404

        finally:
            # Deleting only this uniquely named project cascades to its Tender,
            # items, and match_results. Commodity catalog remains untouched.
            with pool.connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM projects WHERE name = %s;",
                    (project_name,),
                )
