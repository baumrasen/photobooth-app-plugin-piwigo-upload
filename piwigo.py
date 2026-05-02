import logging
import requests
import time
import json
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from photobooth.plugins import hookimpl
from photobooth.plugins.base_plugin import BasePlugin
from .config import PiwigoConfig

logger = logging.getLogger(__name__)

class Piwigo(BasePlugin[PiwigoConfig]):
    def __init__(self):
        super().__init__()
        self._config = PiwigoConfig()

    @hookimpl
    def photobooth_plugin_config(self):
        return PiwigoConfig

    @hookimpl
    def photobooth_plugin_loaded(self, config: PiwigoConfig):
        self._config = config

    @hookimpl
    def start(self):
        logger.info("PIWIGO: Plugin active and ready.")

#    @hookimpl
#    def get_share_links(self, filepath_local, identifier):
#        # Photobooth fragt: "Welche Links hast du für dieses Bild?"
#        # Wir suchen das Item in der DB, um zu sehen, ob wir eine share_url haben.
#        
#        from photobooth.container import container
#        from uuid import UUID
#        
#        links = []
#        try:
#            # Identifier kommt als UUID oder String
#            item_id = UUID(str(identifier))
#            item = container.mediacollection_service.get_item(item_id)
#            
#            if item and item.share_url:
#                # Wenn wir eine URL in der DB haben, geben wir sie zurück
#                links.append(item.share_url)
#                logger.error(f"PIWIGO: Hook returns link: {item.share_url}")
#        except Exception as e:
#            logger.error(f"PIWIGO: Error in get_share_links hook: {e}")
#            
#        return links

    @hookimpl
    def sm_after_transition(self, source, target, event, mediaitem_type):
        if target.id == "completed":
            if not self._config.enabled:
                logger.debug("PIWIGO: Plugin disabled. Skipping upload.")
                return

            actual_type = mediaitem_type.value if hasattr(mediaitem_type, 'value') else str(mediaitem_type)
            if not self._is_upload_enabled(actual_type):
                logger.debug(f"PIWIGO: Upload for media type '{actual_type}' is disabled in config.")
                return

            # Start the upload process in a separate thread to avoid blocking the state machine
            thread = threading.Thread(target=self._handle_upload, args=(mediaitem_type,))
            thread.daemon = True
            thread.start()

    def _is_upload_enabled(self, media_type: str) -> bool:
        normalized = media_type.lower()
        if normalized in ("photo", "image", "picture"):
            return self._config.upload.image
        if normalized == "collage":
            return self._config.upload.collage
        if normalized in ("animation", "gif", "animated"):
            return self._config.upload.animation
        if normalized in ("video", "movie"):
            return self._config.upload.video

        logger.debug(f"PIWIGO: Unknown media type '{media_type}'. Upload skipped.")
        return False

    def _handle_upload(self, mediaitem_type):
        actual_type = mediaitem_type.value if hasattr(mediaitem_type, 'value') else str(mediaitem_type)

        if not self._config.enabled:
            logger.debug("PIWIGO: Plugin disabled in config. Stopping upload handler.")
            return

        if not self._is_upload_enabled(actual_type):
            logger.debug(f"PIWIGO: Upload for media type '{actual_type}' is disabled in config. Stopping upload handler.")
            return

        from photobooth.container import container
        import time
        from datetime import datetime

        # Store hook timestamp in UTC
        hook_trigger_time = datetime.now(timezone.utc)

        # 1. Wait time (collages need time to finish saving)
        # time.sleep(5.0 if actual_type == "collage" else 2.0)

        # 2. Fetch the latest created item and check its timestamp
        max_retries = 30
        retry_delay = 1
        for attempt in range(max_retries):
            try:
                target_item = container.mediacollection_service.get_item_latest()

                if not target_item:
                    logger.debug("PIWIGO: No current item found.")
                    time.sleep(retry_delay)
                    continue

                item_type = getattr(target_item.media_type, 'value', str(target_item.media_type))
                # Normalize created_at to UTC
                item_created_at = target_item.created_at
                if item_created_at.tzinfo is None:
                    item_created_at = item_created_at.replace(tzinfo=timezone.utc)
                else:
                    item_created_at = item_created_at.astimezone(timezone.utc)
                delta = hook_trigger_time - item_created_at
                logger.debug(f"PIWIGO_TIME_CHECK: Latest item type {item_type}, time {item_created_at}, id {target_item.id}, hook time {hook_trigger_time}, delta {delta.total_seconds():.3f}s")

                if item_type != actual_type:
                    logger.debug(f"PIWIGO: Latest item type is {item_type}, expected {actual_type}. Skipping upload.")
                    return

                # Check whether the item is close enough to the hook trigger time
                if abs(delta.total_seconds()) <= 5:
                    logger.info(f"PIWIGO: Success! Latest item found and time-matched. ID: {target_item.id}, created at: {target_item.created_at}, delta {delta.total_seconds():.3f}s")
                    self._do_upload(target_item)
                    return
                else:
                    logger.debug(f"PIWIGO: Item outside time window ({item_created_at} delta {delta.total_seconds():.3f}s), waiting and retrying ({attempt+1}/{max_retries})")
                    time.sleep(retry_delay)
            except Exception as e:
                logger.error(f"PIWIGO_CRITICAL: Error finding image item: {e}")
                time.sleep(retry_delay)

        logger.error("PIWIGO: No matching item found after several attempts. Upload aborted.")

    def _do_upload(self, media_item):
        raw_path = str(media_item.processed) if media_item.processed else str(media_item.captured_original)
        image_path = str(Path(raw_path).absolute())

        # Filename format YYYYMMDD_HHMMSS
        ts = media_item.created_at if hasattr(media_item, 'created_at') else datetime.now()
        new_filename = ts.strftime("%Y%m%d_%H%M%S")

        api_endpoint = f"{self._config.connection.api_url}/ws.php?format=json"
        session = requests.Session()

        try:
            session.post(api_endpoint, data={
                'method': 'pwg.session.login', 'username': self._config.connection.username, 'password': self._config.connection.password
            })
            
            with open(image_path, 'rb') as img:
                cat_id = str(self._config.connection.album_id)
                payload = {
                    'method': 'pwg.images.addSimple',
                    'category': cat_id,
                    'categories': cat_id,
                    'name': new_filename,
                    'level': 0
                }
                res = session.post(api_endpoint, data=payload, files={'image': img})
                
                # Robust JSON parser for "extra data"
                content = res.text
                data = json.loads(content[content.find('{'):content.rfind('}')+1])

            if data.get('stat') == 'ok':
                img_id = data['result']['image_id']
                # Force association & set title
                session.post(api_endpoint, data={
                    'method': 'pwg.images.setInfo',
                    'image_id': img_id,
                    'categories': cat_id,
                    'name': new_filename,
                    'multiple_value_mode': 'replace'
                })
                media_item.share_url = f"{self._config.connection.api_url}/picture.php?/{img_id}"
                logger.info(f"PIWIGO: Upload successful ({new_filename}.jpg)")
            else:
                logger.error(f"PIWIGO: API error: {data}")

        except Exception as e:
            logger.error(f"PIWIGO: Upload error: {e}")
