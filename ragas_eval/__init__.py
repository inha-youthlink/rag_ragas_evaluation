# YouthLink RAG를 RAGAS로 평가하는 패키지
import os

# ragas는 기본으로 사용 통계(모델명 등)를 외부로 전송하고 이 값을 첫 호출 때 캐시하므로, ragas import 전에 끈다
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
