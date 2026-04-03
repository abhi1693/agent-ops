"""Observability app nodes."""

from automation.nodes.apps.base import workflow_app

from .tool.elasticsearch_search import NODE_DEFINITION as ELASTICSEARCH_SEARCH_NODE_DEFINITION
from .tool.prometheus_query import NODE_DEFINITION as PROMETHEUS_QUERY_NODE_DEFINITION
from .trigger.alertmanager_webhook import NODE_DEFINITION as ALERTMANAGER_WEBHOOK_NODE_DEFINITION
from .trigger.kibana_webhook import NODE_DEFINITION as KIBANA_WEBHOOK_NODE_DEFINITION


APP_DEFINITION = workflow_app(
    id="observability",
    label="Observability",
    description="Ingest alerts and query monitoring systems such as Prometheus and Elasticsearch.",
    icon="mdi-chart-areaspline",
    nodes=(
        ALERTMANAGER_WEBHOOK_NODE_DEFINITION,
        KIBANA_WEBHOOK_NODE_DEFINITION,
        PROMETHEUS_QUERY_NODE_DEFINITION,
        ELASTICSEARCH_SEARCH_NODE_DEFINITION,
    ),
    sort_order=30,
)

__all__ = ["APP_DEFINITION"]
