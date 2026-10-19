from dataclasses import dataclass

from costpilot_core.models.matching.match_candidate import MatchCandidate
from costpilot_core.models.matching.match_result import MatchResult
from costpilot_core.models.tender.tender import TenderItem


@dataclass(slots=True)
class TenderItemMatch:
    position_id: int
    item: TenderItem
    result: MatchResult
    candidates: list[MatchCandidate]
