# 평가 테이블을 읽어 성적표·baseline 비교를 만들고 노션·디스코드로 내보냄
from uuid import UUID


def report(run_id: UUID) -> str:
    raise NotImplementedError
