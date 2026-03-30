import os
from json import loads
from unittest.mock import patch

from django.test import TestCase

from automation.models import Workflow
from automation.runtime import execute_workflow
from integrations.models import Secret
from tenancy.models import Environment, Organization, Workspace


class _FakeJsonResponse:
    def __init__(self, payload, *, status=200, content_type="application/json"):
        self._payload = payload
        self._status = status
        self.headers = {"Content-Type": content_type}

    def read(self):
        import json

        return json.dumps(self._payload).encode("utf-8")

    def getcode(self):
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class WorkflowRuntimeTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Acme")
        self.workspace = Workspace.objects.create(
            organization=self.organization,
            name="Operations",
        )
        self.environment = Environment.objects.create(
            workspace=self.workspace,
            name="production",
        )

    def test_execute_workflow_runs_built_in_primitives_end_to_end(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Built-in runtime",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "agent-1",
                        "kind": "agent",
                        "label": "Draft",
                        "config": {
                            "template": "Review {{ trigger.payload.ticket_id }}",
                            "output_key": "draft",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "label": "Done",
                        "config": {
                            "template": "Completed {{ draft }}",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "agent-1"},
                    {"id": "edge-2", "source": "agent-1", "target": "response-1"},
                ],
            },
        )

        run = execute_workflow(
            workflow,
            input_data={"ticket_id": "T-42"},
        )

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "Completed Review T-42")
        self.assertEqual(run.context_data["draft"], "Review T-42")
        self.assertEqual(run.step_count, 3)

    def test_execute_workflow_redacts_secret_values_from_persisted_run_data(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Secret-backed runtime",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "label": "Resolve key",
                        "config": {
                            "tool_name": "secret",
                            "name": "OPENAI_API_KEY",
                            "provider": "environment-variable",
                            "output_key": "credentials.openai",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "label": "Done",
                        "config": {
                            "template": "Resolved {{ credentials.openai }}",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                    {"id": "edge-2", "source": "tool-1", "target": "response-1"},
                ],
            },
        )
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="OPENAI_API_KEY",
            parameters={"variable": "OPENAI_API_KEY"},
        )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-secret"}, clear=False):
            run = execute_workflow(workflow)

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.context_data["credentials"]["openai"], "[redacted secret]")
        self.assertEqual(run.output_data["response"], "Resolved [redacted secret]")
        self.assertEqual(
            run.step_results[1]["result"]["secret"],
            {
                "name": "OPENAI_API_KEY",
                "provider": "environment-variable",
            },
        )
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "secret")

    def test_execute_workflow_supports_legacy_tool_operation_configs(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Legacy secret-backed runtime",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "label": "Resolve key",
                        "config": {
                            "operation": "secret",
                            "name": "OPENAI_API_KEY",
                            "provider": "environment-variable",
                            "output_key": "credentials.openai",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "label": "Done",
                        "config": {
                            "template": "Resolved {{ credentials.openai }}",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                    {"id": "edge-2", "source": "tool-1", "target": "response-1"},
                ],
            },
        )
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="OPENAI_API_KEY",
            parameters={"variable": "OPENAI_API_KEY"},
        )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-secret"}, clear=False):
            run = execute_workflow(workflow)

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"], "Resolved [redacted secret]")
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "secret")

    def test_execute_workflow_fetches_pagerduty_incidents(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="PagerDuty workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "label": "PagerDuty incidents",
                        "config": {
                            "tool_name": "pagerduty_list_incidents",
                            "api_key_name": "PAGERDUTY_API_KEY",
                            "api_key_provider": "environment-variable",
                            "incident_key": "{{ trigger.payload.incident_key }}",
                            "output_key": "pagerduty.incidents",
                            "limit": 10,
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "label": "Done",
                        "config": {
                            "value_path": "pagerduty.incidents",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                    {"id": "edge-2", "source": "tool-1", "target": "response-1"},
                ],
            },
        )
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="PAGERDUTY_API_KEY",
            parameters={"variable": "PAGERDUTY_API_KEY"},
        )

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertIn("/incidents?", request.full_url)
            self.assertIn("incident_key=INC-42", request.full_url)
            self.assertIn("limit=10", request.full_url)
            self.assertIn("statuses%5B%5D=triggered", request.full_url)
            self.assertEqual(request.headers["Authorization"], "Token token=pd-secret")
            return _FakeJsonResponse(
                {
                    "incidents": [
                        {"id": "PD1", "title": "API down"},
                        {"id": "PD2", "title": "Queue backed up"},
                    ]
                }
            )

        with patch.dict(os.environ, {"PAGERDUTY_API_KEY": "pd-secret"}, clear=False):
            with patch("automation.tools.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(workflow, input_data={"incident_key": "INC-42"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"]["count"], 2)
        self.assertEqual(run.context_data["pagerduty"]["incidents"]["incidents"][0]["id"], "PD1")

    def test_execute_workflow_searches_datadog_logs(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Datadog workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "label": "Datadog logs",
                        "config": {
                            "tool_name": "datadog_search_logs",
                            "api_key_name": "DATADOG_API_KEY",
                            "api_key_provider": "environment-variable",
                            "app_key_name": "DATADOG_APP_KEY",
                            "app_key_provider": "environment-variable",
                            "query": "service:api status:error {{ trigger.payload.ticket_id }}",
                            "window_minutes": 30,
                            "limit": 5,
                            "output_key": "datadog.logs",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "label": "Done",
                        "config": {
                            "value_path": "datadog.logs",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                    {"id": "edge-2", "source": "tool-1", "target": "response-1"},
                ],
            },
        )
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="DATADOG_API_KEY",
            parameters={"variable": "DATADOG_API_KEY"},
        )
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="DATADOG_APP_KEY",
            parameters={"variable": "DATADOG_APP_KEY"},
        )

        def fake_urlopen(request, timeout=20):
            self.assertEqual(request.full_url, "https://api.datadoghq.com/api/v2/logs/events/search")
            self.assertEqual(request.headers["Dd-api-key"], "dd-api-secret")
            self.assertEqual(request.headers["Dd-application-key"], "dd-app-secret")
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["filter"]["query"], "service:api status:error T-42")
            self.assertEqual(body["page"]["limit"], 5)
            return _FakeJsonResponse({"data": [{"id": "log-1"}, {"id": "log-2"}]})

        with patch.dict(
            os.environ,
            {"DATADOG_API_KEY": "dd-api-secret", "DATADOG_APP_KEY": "dd-app-secret"},
            clear=False,
        ):
            with patch("automation.tools.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(workflow, input_data={"ticket_id": "T-42"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"]["count"], 2)
        self.assertEqual(run.context_data["datadog"]["logs"]["query"], "service:api status:error T-42")

    def test_execute_workflow_queries_grafana_prometheus(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Grafana workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "label": "Grafana query",
                        "config": {
                            "tool_name": "grafana_query_prometheus",
                            "api_key_name": "GRAFANA_API_KEY",
                            "api_key_provider": "environment-variable",
                            "base_url": "https://grafana.example.com",
                            "datasource_uid": "prom-main",
                            "query": "up{job='api'}",
                            "time": "1711798200",
                            "output_key": "grafana.query",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "label": "Done",
                        "config": {
                            "value_path": "grafana.query",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                    {"id": "edge-2", "source": "tool-1", "target": "response-1"},
                ],
            },
        )
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="GRAFANA_API_KEY",
            parameters={"variable": "GRAFANA_API_KEY"},
        )

        def fake_urlopen(request, timeout=20):
            self.assertIn("/api/datasources/proxy/uid/prom-main/api/v1/query?", request.full_url)
            self.assertIn("query=up%7Bjob%3D%27api%27%7D", request.full_url)
            self.assertIn("time=1711798200", request.full_url)
            self.assertEqual(request.headers["Authorization"], "Bearer grafana-secret")
            return _FakeJsonResponse(
                {
                    "status": "success",
                    "data": {
                        "resultType": "vector",
                        "result": [{"metric": {"job": "api"}, "value": [1711798200, "1"]}],
                    },
                }
            )

        with patch.dict(os.environ, {"GRAFANA_API_KEY": "grafana-secret"}, clear=False):
            with patch("automation.tools.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(workflow)

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[1]["result"]["result_count"], 1)
        self.assertEqual(run.context_data["grafana"]["query"]["status"], "success")

    def test_execute_workflow_queries_prometheus_directly(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Prometheus workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "label": "Prometheus query",
                        "config": {
                            "tool_name": "prometheus_query",
                            "base_url": "https://prometheus.example.com",
                            "bearer_token_name": "PROMETHEUS_API_TOKEN",
                            "bearer_token_provider": "environment-variable",
                            "query": "sum(rate(http_requests_total{job='{{ trigger.payload.job }}'}[5m]))",
                            "time": "1711798200",
                            "output_key": "prometheus.query",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "label": "Done",
                        "config": {
                            "value_path": "prometheus.query",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                    {"id": "edge-2", "source": "tool-1", "target": "response-1"},
                ],
            },
        )
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="PROMETHEUS_API_TOKEN",
            parameters={"variable": "PROMETHEUS_API_TOKEN"},
        )

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertIn("/api/v1/query?", request.full_url)
            self.assertIn("query=sum%28rate%28http_requests_total%7Bjob%3D%27api%27%7D%5B5m%5D%29%29", request.full_url)
            self.assertIn("time=1711798200", request.full_url)
            self.assertEqual(request.headers["Authorization"], "Bearer prom-secret")
            return _FakeJsonResponse(
                {
                    "status": "success",
                    "data": {
                        "resultType": "vector",
                        "result": [{"metric": {"job": "api"}, "value": [1711798200, "4.2"]}],
                    },
                }
            )

        with patch.dict(os.environ, {"PROMETHEUS_API_TOKEN": "prom-secret"}, clear=False):
            with patch("automation.tools.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(workflow, input_data={"job": "api"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "prometheus_query")
        self.assertEqual(run.step_results[1]["result"]["result_count"], 1)
        self.assertEqual(run.context_data["prometheus"]["query"]["status"], "success")

    def test_execute_workflow_searches_elasticsearch(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Elasticsearch workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "label": "Elasticsearch search",
                        "config": {
                            "tool_name": "elasticsearch_search",
                            "base_url": "https://elastic.example.com",
                            "index": "logs-*",
                            "auth_token_name": "ELASTICSEARCH_API_KEY",
                            "auth_token_provider": "environment-variable",
                            "auth_scheme": "ApiKey",
                            "query_json": "{\"size\": 5, \"query\": {\"term\": {\"service.keyword\": \"{{ trigger.payload.service }}\"}}}",
                            "output_key": "elastic.search",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "label": "Done",
                        "config": {
                            "value_path": "elastic.search",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                    {"id": "edge-2", "source": "tool-1", "target": "response-1"},
                ],
            },
        )
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="ELASTICSEARCH_API_KEY",
            parameters={"variable": "ELASTICSEARCH_API_KEY"},
        )

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertEqual(request.full_url, "https://elastic.example.com/logs-*/_search")
            self.assertEqual(request.headers["Authorization"], "ApiKey elastic-secret")
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["size"], 5)
            self.assertEqual(body["query"]["term"]["service.keyword"], "payments-api")
            return _FakeJsonResponse(
                {
                    "took": 12,
                    "hits": {
                        "total": {"value": 2, "relation": "eq"},
                        "hits": [
                            {"_id": "doc-1", "_source": {"message": "first"}},
                            {"_id": "doc-2", "_source": {"message": "second"}},
                        ],
                    },
                    "aggregations": {"levels": {"buckets": [{"key": "error", "doc_count": 2}]}},
                }
            )

        with patch.dict(os.environ, {"ELASTICSEARCH_API_KEY": "elastic-secret"}, clear=False):
            with patch("automation.tools.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(workflow, input_data={"service": "payments-api"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "elasticsearch_search")
        self.assertEqual(run.step_results[1]["result"]["hit_count"], 2)
        self.assertEqual(run.context_data["elastic"]["search"]["total"]["value"], 2)

    def test_execute_workflow_calls_openai_compatible_chat(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="LLM workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "label": "OpenAI-compatible chat",
                        "config": {
                            "tool_name": "openai_compatible_chat",
                            "base_url": "https://llm.example.com/v1",
                            "api_key_name": "OPENAI_COMPATIBLE_API_KEY",
                            "api_key_provider": "environment-variable",
                            "model": "gpt-4.1-mini",
                            "system_prompt": "You are an incident triage assistant.",
                            "user_prompt": "Summarize incident {{ trigger.payload.incident_id }}.",
                            "temperature": "0.2",
                            "max_tokens": "120",
                            "extra_body_json": "{\"response_format\": {\"type\": \"json_object\"}}",
                            "output_key": "llm.response",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "label": "Done",
                        "config": {
                            "value_path": "llm.response",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                    {"id": "edge-2", "source": "tool-1", "target": "response-1"},
                ],
            },
        )
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="OPENAI_COMPATIBLE_API_KEY",
            parameters={"variable": "OPENAI_COMPATIBLE_API_KEY"},
        )

        def fake_urlopen(request, timeout=20):
            self.assertEqual(timeout, 20)
            self.assertEqual(request.full_url, "https://llm.example.com/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer llm-secret")
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["model"], "gpt-4.1-mini")
            self.assertEqual(body["messages"][0]["role"], "system")
            self.assertEqual(body["messages"][1]["content"], "Summarize incident INC-77.")
            self.assertEqual(body["temperature"], 0.2)
            self.assertEqual(body["max_tokens"], 120)
            self.assertEqual(body["response_format"]["type"], "json_object")
            return _FakeJsonResponse(
                {
                    "id": "chatcmpl-123",
                    "model": "gpt-4.1-mini",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {
                                "role": "assistant",
                                "content": "{\"summary\":\"Investigate the failing deployment.\"}",
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 34, "completion_tokens": 12, "total_tokens": 46},
                }
            )

        with patch.dict(os.environ, {"OPENAI_COMPATIBLE_API_KEY": "llm-secret"}, clear=False):
            with patch("automation.tools.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(workflow, input_data={"incident_id": "INC-77"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.step_results[1]["result"]["tool_name"], "openai_compatible_chat")
        self.assertEqual(run.output_data["response"]["text"], "{\"summary\":\"Investigate the failing deployment.\"}")
        self.assertEqual(run.context_data["llm"]["response"]["usage"]["total_tokens"], 46)

    def test_execute_workflow_sends_slack_message(self):
        workflow = Workflow.objects.create(
            environment=self.environment,
            name="Slack workflow",
            definition={
                "nodes": [
                    {
                        "id": "trigger-1",
                        "kind": "trigger",
                        "label": "Manual",
                        "position": {"x": 32, "y": 40},
                    },
                    {
                        "id": "tool-1",
                        "kind": "tool",
                        "label": "Slack message",
                        "config": {
                            "tool_name": "slack_send_message",
                            "bot_token_name": "SLACK_BOT_TOKEN",
                            "bot_token_provider": "environment-variable",
                            "channel": "#ops-alerts",
                            "text": "Incident {{ trigger.payload.incident_id }} needs attention",
                            "thread_ts": "1711798200.100200",
                            "output_key": "slack.delivery",
                        },
                        "position": {"x": 320, "y": 40},
                    },
                    {
                        "id": "response-1",
                        "kind": "response",
                        "label": "Done",
                        "config": {
                            "value_path": "slack.delivery",
                        },
                        "position": {"x": 608, "y": 40},
                    },
                ],
                "edges": [
                    {"id": "edge-1", "source": "trigger-1", "target": "tool-1"},
                    {"id": "edge-2", "source": "tool-1", "target": "response-1"},
                ],
            },
        )
        Secret.objects.create(
            environment=self.environment,
            provider="environment-variable",
            name="SLACK_BOT_TOKEN",
            parameters={"variable": "SLACK_BOT_TOKEN"},
        )

        def fake_urlopen(request, timeout=20):
            self.assertEqual(request.full_url, "https://slack.com/api/chat.postMessage")
            self.assertEqual(request.headers["Authorization"], "Bearer slack-secret")
            body = loads(request.data.decode("utf-8"))
            self.assertEqual(body["channel"], "#ops-alerts")
            self.assertEqual(body["text"], "Incident INC-77 needs attention")
            self.assertEqual(body["thread_ts"], "1711798200.100200")
            return _FakeJsonResponse(
                {
                    "ok": True,
                    "channel": "C12345",
                    "ts": "1711798300.000100",
                    "message": {"text": body["text"]},
                }
            )

        with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "slack-secret"}, clear=False):
            with patch("automation.tools.urlopen", side_effect=fake_urlopen):
                run = execute_workflow(workflow, input_data={"incident_id": "INC-77"})

        self.assertEqual(run.status, "succeeded")
        self.assertEqual(run.output_data["response"]["channel"], "C12345")
        self.assertEqual(run.context_data["slack"]["delivery"]["ts"], "1711798300.000100")
