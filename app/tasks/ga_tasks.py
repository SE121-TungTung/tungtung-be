import logging
from uuid import UUID
from app.core.celery_app import celery_app
from app.schemas.ga_schedule import GAScheduleRequest
from app.services.schedule.ga_service import ga_schedule_service

logger = logging.getLogger(__name__)

@celery_app.task(name="execute_ga_task")
def execute_ga_task(run_id_str: str, request_dict: dict) -> None:
    """
    Celery task to run the Genetic Algorithm schedule optimizer in the background.
    """
    logger.info(f"Starting Celery GA task for run_id: {run_id_str}")
    try:
        run_id = UUID(run_id_str)
        # Reconstruct the Pydantic request object
        request = GAScheduleRequest(**request_dict)
        
        # Delegate execution to service
        ga_schedule_service.execute_ga_background(run_id, request)
        logger.info(f"Celery GA task completed for run_id: {run_id_str}")
    except Exception as e:
        logger.exception(f"Error in Celery GA task for run_id {run_id_str}: {e}")
        raise
