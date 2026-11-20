import datetime
from typing import List, Optional

import config
from src.logger import logger
from src.upload.youtube import can_upload_now, load_upload_history


def get_current_time() -> datetime.time:
    """Get current local time."""
    return datetime.datetime.now().time()


def parse_time_str(time_str: str) -> datetime.time:
    """Parse HH:MM string to time object."""
    parts = time_str.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return datetime.time(hour=hour, minute=minute)


def find_most_recent_slot(schedule_times: List[str]) -> Optional[datetime.datetime]:
    """
    Find the most recent scheduled upload slot that is in the past.
    Returns a datetime object representing the slot start.
    """
    now = datetime.datetime.now()
    today_slots = []
    
    for t_str in schedule_times:
        try:
            slot_t = parse_time_str(t_str)
            # Create datetime for today's slot
            slot_dt = datetime.datetime.combine(now.date(), slot_t)
            today_slots.append(slot_dt)
            
            # Also add yesterday's slot to handle wraps across midnight
            yesterday_dt = slot_dt - datetime.timedelta(days=1)
            today_slots.append(yesterday_dt)
        except Exception as e:
            logger.error(f"Failed to parse schedule time '{t_str}': {e}")
            
    # Sort slots descending (most recent first)
    today_slots.sort(reverse=True)
    
    # Filter for slots in the past
    past_slots = [slot for slot in today_slots if slot <= now]
    
    if past_slots:
        return past_slots[0]
    return None


def has_uploaded_since(slot_time: datetime.datetime) -> bool:
    """Check if we have completed a successful upload since the specified slot time."""
    history = load_upload_history()
    
    for record in history:
        if record.get("status") == "success":
            try:
                # Parse record timestamp as UTC
                record_time = datetime.datetime.fromisoformat(record["timestamp"])
                # Convert slot_time to UTC for comparison
                slot_utc = slot_time.astimezone(datetime.timezone.utc)
                
                if record_time >= slot_utc:
                    return True
            except Exception as e:
                logger.warning(f"Failed to parse timestamp in record {record}: {e}")
                continue
    return False


def check_scheduler_run(force: bool = False, ignore_limits: bool = False) -> bool:
    """
    Determine if the pipeline should run right now.
    
    Args:
        force: If True, ignore schedule slots.
        ignore_limits: If True, ignore the 24h upload limit.
        
    Returns:
        True if the pipeline should run and upload, False otherwise.
    """
    if not ignore_limits and not can_upload_now():
        logger.info(f"Scheduler Check: Blocked (daily limit of {config.MAX_VIDEOS_PER_DAY} uploads reached)")
        return False
        
    if force or ignore_limits:
        logger.info(f"Scheduler Check: Forced run requested (ignore_limits={ignore_limits})")
        return True
        
    schedule_times = config.UPLOAD_SCHEDULE_TIMES
    if not schedule_times:
        logger.info("Scheduler Check: Run permitted (no schedule times configured)")
        return True
        
    recent_slot = find_most_recent_slot(schedule_times)
    if not recent_slot:
        logger.info("Scheduler Check: Blocked (no past schedule slots found)")
        return False
        
    # Check if we already uploaded for this slot
    logger.info(f"Scheduler Check: Most recent slot was {recent_slot.strftime('%Y-%m-%d %H:%M')}")
    if has_uploaded_since(recent_slot):
        logger.info(f"Scheduler Check: Blocked (already uploaded for slot {recent_slot.strftime('%H:%M')})")
        return False
        
    # We haven't uploaded since the most recent slot, so run now!
    logger.info(f"Scheduler Check: Approved (no upload found since slot {recent_slot.strftime('%H:%M')})")
    return True
