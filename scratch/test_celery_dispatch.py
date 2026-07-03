import sys
import os
from uuid import uuid4
from datetime import date

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.schemas.ga_schedule import GAScheduleRequest

def test_pydantic_serialization():
    print("========== START SERIALIZATION TEST ==========")
    req = GAScheduleRequest(
        start_date=date(2026, 7, 3),
        end_date=date(2026, 7, 10),
        class_ids=[uuid4(), uuid4()],
        population_size=10,
        generations=10,
        crossover_rate=0.8,
        mutation_rate=0.1,
    )
    
    from uuid import UUID
    # Dump to dict (simulating Celery transport)
    dumped = req.model_dump()
    # Serialize date & UUID to JSON types (strings) as Celery json serializer does
    import json
    # Use custom encoder to serialize UUID and date to JSON strings
    class CustomEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (date, UUID)):
                return str(obj)
            return super().default(obj)
            
    json_str = json.dumps(dumped, cls=CustomEncoder)
    serialized_dict = json.loads(json_str)
    
    # In Celery task we reconstruct it
    reconstructed = GAScheduleRequest(**serialized_dict)
    print("Reconstructed successfully!")
    print("Start date type:", type(reconstructed.start_date), reconstructed.start_date)
    print("Class IDs type:", type(reconstructed.class_ids[0]), reconstructed.class_ids[0])
    
    assert reconstructed.start_date == req.start_date
    assert reconstructed.class_ids[0] == req.class_ids[0]
    print("All serialization assertions passed successfully!")

if __name__ == "__main__":
    test_pydantic_serialization()
