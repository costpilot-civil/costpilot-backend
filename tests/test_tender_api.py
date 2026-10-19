from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app

# Entirely synthetic engineering data; no company tender text.
SAMPLE_TENDER = """\
<?xml version="1.0" encoding="UTF-8"?>
<GAEB xmlns="http://www.gaeb.de/GAEB_DA_XML/200407">
  <Award>
    <BoQ>
      <BoQInfo>
        <BoQBkdn><Type>BoQLevel</Type><Length>2</Length></BoQBkdn>
        <BoQBkdn><Type>BoQLevel</Type><Length>2</Length></BoQBkdn>
        <BoQBkdn><Type>Item</Type><Length>3</Length></BoQBkdn>
      </BoQInfo>
      <BoQBody>
        <BoQCtgy RNoPart="1">
          <BoQCatInfo><LblTx>Concrete works</LblTx></BoQCatInfo>
          <BoQBody>
            <BoQCtgy RNoPart="2">
              <BoQCatInfo><LblTx>Foundations</LblTx></BoQCatInfo>
              <BoQBody>
                <Itemlist>
                  <Item RNoPart="1">
                    <Qty>15.50</Qty><QU>m3</QU>
                    <Description><CompleteText>
                      <OutlineText>Concrete C30/37</OutlineText>
                      <DetailTxt>Synthetic foundation concrete</DetailTxt>
                    </CompleteText></Description>
                  </Item>
                  <Item RNoPart="2">
                    <Qty>5.25</Qty><QU>t</QU>
                    <Description><CompleteText>
                      <OutlineText>Reinforcing steel</OutlineText>
                      <DetailTxt>Synthetic reinforcement</DetailTxt>
                    </CompleteText></Description>
                  </Item>
                </Itemlist>
              </BoQBody>
            </BoQCtgy>
          </BoQBody>
        </BoQCtgy>
      </BoQBody>
    </BoQ>
  </Award>
</GAEB>
"""


def test_tender_upload_and_readback() -> None:
    app = create_app()
    project_name = f"TEST_TENDER_{uuid4().hex}"

    with TestClient(app) as client:
        pool = app.state.db_pool
        try:
            response = client.post("/projects", json={"name": project_name})
            assert response.status_code == 201, response.text
            project_id = response.json()["id"]

            response = client.post(
                f"/projects/{project_id}/tenders",
                files={
                    "file": ("synthetic.x83", SAMPLE_TENDER.encode(), "application/xml")
                },
            )
            assert response.status_code == 201, response.text
            document = response.json()
            tender_id = document["id"]
            assert document["project_id"] == project_id
            assert document["status"] == "PARSED"

            response = client.get(f"/projects/{project_id}/tenders")
            assert response.status_code == 200
            assert any(doc["id"] == tender_id for doc in response.json())

            response = client.get(f"/projects/{project_id}/tenders/{tender_id}")
            assert response.status_code == 200, response.text
            detail = response.json()
            nodes = detail["structure"]["nodes"]
            assert len(nodes) == 1
            assert nodes[0]["name"] == "Concrete works"
            assert nodes[0]["oz"] == "01"
            nested = nodes[0]["children"][0]
            assert nested["name"] == "Foundations"
            assert nested["oz"] == "01.02"
            items = nested["children"]
            assert [item["oz"] for item in items] == ["01.02.001", "01.02.002"]
            assert Decimal(str(items[0]["quantity"])) == Decimal("15.50")

            references = detail["positions"]
            assert len(references) == 2
            assert references[0]["path"] == [0, 0, 0]
            assert references[1]["path"] == [0, 0, 1]
            assert references[0]["position_id"] > 0

            response = client.get(f"/projects/{project_id}/tenders/{tender_id}/items")
            assert response.status_code == 200, response.text
            flat_items = response.json()
            assert len(flat_items) == 2
            assert flat_items[0]["position_id"] == references[0]["position_id"]
            assert flat_items[0]["item"]["short_text"] == "Concrete C30/37"

            response = client.get(f"/projects/{project_id}/tenders/999999999")
            assert response.status_code == 404

        finally:
            # A unique name protects cleanup even if creation succeeds but the response fails.
            with pool.connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM projects WHERE name = %s;",
                    (project_name,),
                )


def test_tender_upload_validation() -> None:
    app = create_app()
    project_name = f"TEST_TENDER_{uuid4().hex}"
    with TestClient(app) as client:
        pool = app.state.db_pool
        try:
            response = client.post("/projects", json={"name": project_name})
            assert response.status_code == 201, response.text
            project_id = response.json()["id"]

            response = client.post(
                f"/projects/{project_id}/tenders",
                files={"file": ("bad.txt", b"text", "text/plain")},
            )
            assert response.status_code == 415

            response = client.post(
                f"/projects/{project_id}/tenders",
                files={"file": ("broken.xml", b"<GAEB>", "application/xml")},
            )
            assert response.status_code == 422

            response = client.get(f"/projects/{project_id}/tenders")
            assert response.status_code == 200
            assert response.json() == []
        finally:
            with pool.connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM projects WHERE name = %s;",
                    (project_name,),
                )
