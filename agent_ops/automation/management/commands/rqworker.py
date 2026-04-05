from __future__ import annotations

import logging

from django_rq.management.commands.rqworker import Command as BaseRQWorkerCommand


DEFAULT_QUEUES = ("high", "default", "low")

logger = logging.getLogger("automation.rqworker")


class Command(BaseRQWorkerCommand):
    def handle(self, *args, **options):
        options["with_scheduler"] = True

        if len(args) < 1:
            queues = ", ".join(DEFAULT_QUEUES)
            logger.warning(
                "No queues have been specified. This worker will service the following queues by default: %s",
                queues,
            )
            args = DEFAULT_QUEUES

        super().handle(*args, **options)
