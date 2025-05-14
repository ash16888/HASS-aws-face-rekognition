from __future__ import annotations

from collections import Counter
import io
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
import voluptuous as vol
from homeassistant.components.image_processing import (
    ATTR_CONFIDENCE,
    CONF_CONFIDENCE,
    CONF_ENTITY_ID,
    CONF_NAME,
    CONF_SOURCE,
    DEFAULT_CONFIDENCE,
    DOMAIN,
    PLATFORM_SCHEMA,
    ImageProcessingEntity,
)
from homeassistant.core import split_entity_id
from aws_requests_auth.aws_auth import AWSRequestsAuth  # type: ignore
from PIL import Image, ImageDraw, UnidentifiedImageError
from homeassistant.util.pil import draw_box

_LOGGER = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Configuration keys
CONF_REGION = "region_name"
CONF_ACCESS_KEY_ID = "aws_access_key_id"
CONF_SECRET_ACCESS_KEY = "aws_secret_access_key"

CONF_COLLECTION_ID = "collection_id"
CONF_SIMILARITY = "similarity_threshold"

CONF_SAVE_FILE_FORMAT = "save_file_format"
CONF_SAVE_FILE_FOLDER = "save_file_folder"
CONF_SAVE_TIMESTAMPTED_FILE = "save_timestamped_file"
CONF_ALWAYS_SAVE_LATEST_FILE = "always_save_latest_file"
CONF_SHOW_BOXES = "show_boxes"
DEFAULT_REGION = "us-east-1"
DEFAULT_CONFIDENCE = 90.0  # similarity threshold default

SUPPORTED_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "ca-central-1",
    "eu-west-1",
    "eu-central-1",
    "eu-west-2",
    "eu-west-3",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-northeast-2",
    "ap-northeast-1",
    "ap-south-1",
    "sa-east-1",
]

DATETIME_FORMAT = "%Y-%m-%d_%H.%M.%S"

MIN_SIMILARITY = 0.0

EVENT_FACE_RECOGNISED = "rekognition.face_recognised"

# ──────────────────────────────────────────────────────────────────────────────
# Validation schema
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_ACCESS_KEY_ID): cv.string,
        vol.Required(CONF_SECRET_ACCESS_KEY): cv.string,
        vol.Optional(CONF_REGION, default=DEFAULT_REGION): vol.In(SUPPORTED_REGIONS),
        vol.Required(CONF_COLLECTION_ID): cv.string,
        vol.Optional(CONF_SIMILARITY, default=DEFAULT_CONFIDENCE): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=100)
        ),
        # keep original optional keys for saving images, etc.
        vol.Optional(CONF_SAVE_FILE_FOLDER): cv.isdir,
        vol.Optional(CONF_SAVE_FILE_FORMAT, default="jpg"): vol.In(["jpg", "png"]),
        vol.Optional(CONF_SAVE_TIMESTAMPTED_FILE, default=True): cv.boolean,
        vol.Optional(CONF_ALWAYS_SAVE_LATEST_FILE, default=True): cv.boolean,
        vol.Optional(CONF_SHOW_BOXES, default=False): cv.boolean,
    }
)

# ──────────────────────────────────────────────────────────────────────────────
# Setup platform

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up Rekognition Face Recognition."""

    import boto3  # late import so module is optional in Home Assistant core

    aws_config = {
        "region_name": config[CONF_REGION],
        "aws_access_key_id": config[CONF_ACCESS_KEY_ID],
        "aws_secret_access_key": config[CONF_SECRET_ACCESS_KEY],
    }

    _LOGGER.debug("Connecting to AWS Rekognition in %s", aws_config["region_name"])
    rekognition_client = boto3.client("rekognition", **aws_config)

    save_file_folder = config.get(CONF_SAVE_FILE_FOLDER)
    if save_file_folder:
        save_file_folder = Path(save_file_folder)

    entities = []
    for camera in config[CONF_SOURCE]:
        entities.append(
            FaceRecognitionEntity(
                rekognition_client=rekognition_client,
                collection_id=config[CONF_COLLECTION_ID],
                similarity=config[CONF_SIMILARITY],
                save_file_format=config.get(CONF_SAVE_FILE_FORMAT),
                save_file_folder=save_file_folder,
                save_timestamped_file=config.get(CONF_SAVE_TIMESTAMPTED_FILE),
                always_save_latest_file=config.get(CONF_ALWAYS_SAVE_LATEST_FILE),
                show_boxes=config.get(CONF_SHOW_BOXES),
                camera_entity=camera.get(CONF_ENTITY_ID),
                name=camera.get(CONF_NAME),
            )
        )

    add_devices(entities)


# ──────────────────────────────────────────────────────────────────────────────
# Entity class

class FaceRecognitionEntity(ImageProcessingEntity):
    """Search a Rekognition collection for known faces."""

    def __init__(
        self,
        rekognition_client,
        collection_id: str,
        similarity: float,
        save_file_format: str | None,
        save_file_folder: Path | None,
        save_timestamped_file: bool,
        always_save_latest_file: bool,
        show_boxes: bool,
        camera_entity: str,
        name: str | None = None,
    ) -> None:
        super().__init__()
        self._client = rekognition_client
        self._collection_id = collection_id
        self._similarity_threshold = similarity
        self._camera_entity = camera_entity
        self._name = name or f"rekognition_face_{split_entity_id(camera_entity)[1]}"

        # state & attrs
        self._state: int | None = None
        self._matches: List[Dict[str, Any]] = []
        self._last_detection: str | None = None

        # image saving
        self._save_file_format = save_file_format
        self._save_file_folder = save_file_folder
        self._save_timestamped_file = save_timestamped_file
        self._always_save_latest_file = always_save_latest_file
        self._show_boxes = show_boxes
        self._image = None

    # ───────── ImageProcessingEntity overrides ─────────

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        """Number of recognised faces in the last frame."""
        return self._state

    @property
    def camera_entity(self):
        return self._camera_entity

    @property
    def should_poll(self):
        return False

    @property
    def unit_of_measurement(self):
        return "faces"

    @property
    def extra_state_attributes(self):
        attrs = {
            "collection_id": self._collection_id,
            "similarity_threshold": self._similarity_threshold,
            "matches": self._matches,
        }
        if self._last_detection:
            attrs["last_face_recognition"] = self._last_detection
        return attrs

    # ───────── Core logic ─────────
    def process_image(self, image_bytes):
            """Send frame to AWS Rekognition and process the response."""
            try:
                try:
                    img_pil = Image.open(io.BytesIO(image_bytes))
                    self._image = img_pil
                except UnidentifiedImageError:
                    _LOGGER.error(f"'{self.entity_id}': The image could not be recognized.")
                    self._image = None
                    return
                except Exception as e:
                    _LOGGER.error(f"'{self.entity_id}': Error opening image: {e}")
                    self._image = None
                    return
                response = self._client.search_faces_by_image(
                    CollectionId=self._collection_id,
                    Image={"Bytes": image_bytes},
                    FaceMatchThreshold=self._similarity_threshold,
                    MaxFaces=5,
                )
                _LOGGER.debug(f"'{self.entity_id}': Call AWS Rekognition API successful. Response: {response}")

                self._matches = []
                for match in response.get("FaceMatches", []):
                    similarity = match.get("Similarity", 0.0)
                    face_data = match.get("Face", {}) 
                    ext_id = face_data.get("ExternalImageId", "unknown")
                    face_id = face_data.get("FaceId")
                    bounding_box = face_data.get("BoundingBox")
                    self._matches.append(
                        {
                            "external_image_id": ext_id,
                            "face_id": face_id,
                            "similarity": round(similarity, 2),
                            "bounding_box": bounding_box
                        }
                    )
                self._state = len(self._matches)
                if self._state > 0:
                    _LOGGER.info(f"'{self.entity_id}': Successfully matched {self._state} face(faces).")
                else:
                    _LOGGER.info(f"'{self.entity_id}':Faces from the collection are not matched (although faces may have been detected by AWS Rekognition in the image). State is 0.")

            except self._client.exceptions.InvalidParameterException as e:
                error_message = str(e).lower()
                if "no faces in the image" in error_message or \
                "there are no faces in the image" in error_message:
                    _LOGGER.info(
                        f"'{self.entity_id}': AWS Rekognition reported that there were no faces in the provided image. Setting state to 0. Error: {e}"
                    )
                    self._matches = []
                    self._state = 0
                else:
                    _LOGGER.error(
                        f"'{self.entity_id}': AWS Rekognition InvalidParameterException during SearchFacesByImage: {e}"
                    )
                    self._matches = [] 
                    self._state = 0 
            except Exception as e:
                _LOGGER.error(
                    f"'{self.entity_id}': Common error during AWS Rekognition SearchFacesByImage: {e}"
                )
                self._matches = []
                self._state = 0
            _LOGGER.debug(f"'{self.entity_id}': Internal state after processing an API call: {self._state}, Matches: {len(self._matches)}")

            if self._state and self._state > 0:
                self._last_detection = dt_util.now().isoformat()
                for match_data in self._matches:
                    event_data = match_data.copy()
                    event_data["entity_id"] = self.entity_id
                    event_data["timestamp"] = self._last_detection
                    self.hass.bus.fire(EVENT_FACE_RECOGNISED, event_data)
                    _LOGGER.debug(f"'{self.entity_id}': Event generated {EVENT_FACE_RECOGNISED} with data: {event_data}")
            elif self._state == 0:
                _LOGGER.info(f"'{self.entity_id}': The final state is 0. Event '{EVENT_FACE_RECOGNISED}' will not be generated.")

            # Убедимся, что self._image было успешно установлено перед попыткой сохранения
            if self._image and self._save_file_folder and (
                (self._matches and len(self._matches) > 0) or self._always_save_latest_file
            ):
                self._save_annotated_image()
                _LOGGER.debug(f"'{self.entity_id}': The process of saving the annotated image has started.")
            elif not self._image and self._save_file_folder:
                _LOGGER.warning(f"'{self.entity_id}': The process of saving the image was skipped because self._image is not set (possibly due to an error loading the image).")
            _LOGGER.debug(f"'{self.entity_id}': Image processing complete.")
        # ───────── Helpers ─────────

    def _save_annotated_image(self):
            """Draw bounding boxes around recognised faces and save the image."""
            if not self._image:
                _LOGGER.debug(f"'{getattr(self, 'entity_id', self._name)}': _save_annotated_image aborted, self._image is None.")
                return

            if not self.entity_id:
                _LOGGER.error(f"'{self._name or 'UnknownRekognitionEntity'}': entity_id is not available, cannot save image because object_id cannot be derived.")
                return

            try:
                current_object_id = split_entity_id(self.entity_id)[1]
            except Exception as e:
                _LOGGER.error(f"'{self.entity_id}': Error splitting entity_id to get object_id: {e}")
                return

            img = self._image.convert("RGB")
            draw = ImageDraw.Draw(img)

            for match in self._matches:
                bbox = match.get("bounding_box") or match.get("Face", {}).get("BoundingBox")
                if not bbox or not self._show_boxes:
                    continue
                img_width, img_height = img.size
                x_min_abs = bbox["Left"] * img_width
                y_min_abs = bbox["Top"] * img_height
                box_width_abs = bbox["Width"] * img_width
                box_height_abs = bbox["Height"] * img_height

                y_min_rel = bbox["Top"]
                x_min_rel = bbox["Left"]
                y_max_rel = bbox["Top"] + bbox["Height"]
                x_max_rel = bbox["Left"] + bbox["Width"]

                draw_box(
                    draw,
                    (y_min_rel, x_min_rel, y_max_rel, x_max_rel),
                    img_width,
                    img_height,
                    text=f"{match['external_image_id']}: {match['similarity']:.1f}%",
                )

            if not self._save_file_folder.exists():
                try:
                    self._save_file_folder.mkdir(parents=True, exist_ok=True)
                    _LOGGER.info(f"'{self.entity_id}': Created save folder: {self._save_file_folder}")
                except Exception as e:
                    _LOGGER.error(f"'{self.entity_id}': Failed to create save folder {self._save_file_folder}: {e}")
                    return

            filename_latest = (
                self._save_file_folder / f"{current_object_id}_latest.{self._save_file_format or 'jpg'}"
            )
            try:
                img.save(filename_latest)
                _LOGGER.debug(f"'{self.entity_id}': Saved annotated image to %s", filename_latest)
            except Exception as e:
                _LOGGER.error(f"'{self.entity_id}': Failed to save latest image to %s: %s", filename_latest, e)

            if self._matches and self._save_timestamped_file:
                ts = dt_util.now().strftime(DATETIME_FORMAT)
                filename_timestamped = (
                    self._save_file_folder / f"{current_object_id}_{ts}.{self._save_file_format or 'jpg'}"
                )
                try:
                    img.save(filename_timestamped)
                    _LOGGER.info(f"'{self.entity_id}': Saved timestamped image to %s", filename_timestamped)
                except Exception as e:
                    _LOGGER.error(f"'{self.entity_id}': Failed to save timestamped image to %s: %s", filename_timestamped, e)
