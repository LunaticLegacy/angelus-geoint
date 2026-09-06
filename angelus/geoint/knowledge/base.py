"""Static, auditable drought knowledge without external retrieval infrastructure."""
from __future__ import annotations

from typing import Any


class KnowledgeError(KeyError):
    pass


_DOCUMENTS = (
    {"id": "drought-indicator-triangulation", "title": "干旱胁迫的多源证据三角校验", "tags": ["干旱", "NDVI", "降水", "土壤湿度", "证据"], "excerpt": "植被、降水与土壤水分指标应按时间、空间尺度和不确定性共同解释；单一指标异常不足以独立确证农业干旱胁迫。", "content": "将植被指数异常、降水距平、土壤湿度或蒸散发指标对齐到同一季节窗口和分析单元。记录各数据源的时间覆盖、分辨率、重采样方法和缺测处理。出现冲突时，应把冲突保留为证据限制，而不是强行合成为确定结论。", "source": "Angelus curated operational guidance", "year": 2026},
    {"id": "drought-evidence-provenance", "title": "农业干旱证据的可追溯性清单", "tags": ["证据", "溯源", "资产", "派生", "AOI"], "excerpt": "每项结论至少关联原始资产、派生任务或参考知识；结论应能回到会话、资产版本和空间范围。", "content": "记录资产 ID 与版本哈希、派生任务 ID、AOI/几何、指标定义、单位、时间窗口、可信度与已知限制。不要把地图渲染效果或未经验证的 Agent 叙述当作数据证据。", "source": "Angelus curated operational guidance", "year": 2026},
    {"id": "ndvi-drought-caveats", "title": "NDVI 作为干旱胁迫线索的限制", "tags": ["NDVI", "植被", "物候", "干旱"], "excerpt": "NDVI 下降可提示植被胁迫，但也可能来自物候变化、作物类型、云/阴影、管理措施或传感器差异。", "content": "使用基准期或同物候阶段比较，并检查云掩膜、观测密度和地表覆盖。对高覆盖植被的饱和效应保持谨慎。NDVI 更适合作为与降水、土壤水分等联合解释的一个证据分量。", "source": "Tucker, 1979; Angelus curated operational guidance", "year": 1979},
    {"id": "precipitation-soil-moisture-caveats", "title": "降水与土壤水分数据的尺度限制", "tags": ["降水", "土壤水分", "CHIRPS", "尺度"], "excerpt": "格网降水和遥感土壤水分产品存在空间代表性、延迟和模型误差；不能直接等同于田块实况。", "content": "报告产品名称、版本、单位、累积窗口和格网分辨率。将区域尺度结论与田块尺度结论区分开；必要时以站点、灌溉信息或田间观测进行校验。", "source": "Funk et al., 2015; Angelus curated operational guidance", "year": 2015},
)


class DroughtKnowledgeBase:
    """Expose a small bundled corpus through deterministic lexical search."""

    @staticmethod
    def _public(document: dict[str, Any], include_content: bool = False) -> dict[str, Any]:
        keys = ("id", "title", "tags", "excerpt", "source", "year") + (("content",) if include_content else ())
        return {key: document[key] for key in keys}

    def search(self, query: object, limit: int = 5) -> list[dict[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            raise KnowledgeError("query is required")
        bounded = max(1, min(int(limit), 10)); terms = [term for term in query.lower().split() if term]
        needle = query.lower().strip()
        ranked = []
        for document in _DOCUMENTS:
            haystack = " ".join([document["title"], document["excerpt"], document["content"], *document["tags"]]).lower()
            score = int(needle in haystack) * 10 + sum(term in haystack for term in terms)
            if score: ranked.append((score, document))
        return [self._public(document) for _, document in sorted(ranked, key=lambda item: (-item[0], item[1]["id"]))[:bounded]]

    def read(self, document_id: object) -> dict[str, Any]:
        if not isinstance(document_id, str):
            raise KnowledgeError("document id is required")
        document = next((item for item in _DOCUMENTS if item["id"] == document_id), None)
        if document is None:
            raise KnowledgeError(document_id)
        return self._public(document, include_content=True)

    def exists_many(self, identifiers: list[str]) -> bool:
        known = {document["id"] for document in _DOCUMENTS}
        return set(identifiers).issubset(known)
