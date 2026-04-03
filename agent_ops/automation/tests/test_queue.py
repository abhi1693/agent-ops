from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from automation.queue import (
    WORKFLOW_QUEUE_DEFAULT,
    WORKFLOW_QUEUE_HIGH,
    get_workflow_queue_name,
    get_workers_for_queue,
)


class WorkflowQueueTests(SimpleTestCase):
    def test_get_workers_for_queue_counts_only_workers_listening_to_target_queue(self):
        default_worker = Mock()
        default_worker.queue_names.return_value = [WORKFLOW_QUEUE_DEFAULT]
        high_worker = Mock()
        high_worker.queue_names.return_value = [WORKFLOW_QUEUE_HIGH, WORKFLOW_QUEUE_DEFAULT]

        with patch("automation.queue.get_connection", return_value=object()), patch(
            "automation.queue.Worker.all",
            return_value=[default_worker, high_worker],
        ):
            self.assertEqual(get_workers_for_queue(WORKFLOW_QUEUE_HIGH), 1)
            self.assertEqual(get_workers_for_queue(WORKFLOW_QUEUE_DEFAULT), 2)

    def test_get_workflow_queue_name_always_returns_default(self):
        self.assertEqual(get_workflow_queue_name("workflow"), WORKFLOW_QUEUE_DEFAULT)
        self.assertEqual(get_workflow_queue_name("node_preview"), WORKFLOW_QUEUE_DEFAULT)
