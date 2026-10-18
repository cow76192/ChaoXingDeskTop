"""Shared provider identities; protocol implementations remain in vendor."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    title: str
    prefix: str
    secret: str


PROVIDERS = (
    ProviderSpec('TikuGo', 'GO 题库', 'go', 'go_authorization'),
    ProviderSpec('TikuYanxi', '言溪题库', 'yanxi', 'yanxi_tokens'),
    ProviderSpec('TikuLike', 'LIKE 知识库', 'like', 'like_tokens'),
    ProviderSpec('TikuAdapter', '自定义题库 Adapter', 'adapter', 'adapter_url'),
    ProviderSpec('TikuDeclarative', '声明式 JSON 题库', 'declarative', 'declarative_token'),
)
PROVIDER_SPECS = {spec.id: spec for spec in PROVIDERS}
