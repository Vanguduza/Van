"""Native pre57 mission fixtures for intentionally old migration-test databases.

The real migration tests need factual missions/events on schema45/46. A current
producer also requires the new learning queue, which did not exist in that era.
This fixture supplies only the old producer contract; production has no fallback.
"""
from van_gateway.mission.service import MissionService

class PreLearningMissionService(MissionService):
    @staticmethod
    async def _enqueue_learning(db, mission_id, stage, now):
        return 0  # Not a modern delivery generation; these fixtures have no learning sink.
