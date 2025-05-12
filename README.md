# Amazon Rekognition for Home Assistant
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)

Face recogntion with [Amazon Rekognition](https://aws.amazon.com/rekognition/).  The state is the count of faces recognized from your AWS Rekognition Face Collection, meeting a configured similarity threshold. 
Key attributes include: matches: A list of recognized faces, each with external_image_id, similarity, and bounding_box. last_face_recognition: Timestamp of the latest recognition. collection_id and similarity_threshold.
An rekognition.face_recognised event fires for each matched face, providing its external_image_id, similarity, entity_id, and timestamp.
Optionally, images with bounding boxes drawn on recognized faces can be saved.

**Note** that in order to prevent accidental over-billing, the component will not scan images automatically, but requires you to call the `image_processing.scan` service.

**Pricing:** As part of the [AWS Free Tier](https://aws.amazon.com/rekognition/pricing/), you can get started with Amazon Rekognition Image for free. Upon sign-up, new Amazon Rekognition customers can analyze 5,000 images per month for the first 12 months. After that price is around $1 for 1000 images.

## Setup
For advice on getting your Amazon credentials see the [Polly docs](https://www.home-assistant.io/components/tts.amazon_polly/).

Place the `custom_components` folder in your configuration directory (or add its contents to an existing custom_components folder). Add to your `configuration.yaml`:

```yaml
image_processing:
  - platform: amazon_rekognition
    aws_access_key_id: AWS_ACCESS_KEY_ID
    aws_secret_access_key: AWS_SECRET_ACCESS_KEY
    region_name: eu-west-1 # optional region, default is us-east-1
    similarity_threshold: 90 # OPTIONAL: default 90 (0‑100)
    collection_id: homeassistant_faces    
    save_file_format: png
    save_file_folder: /config/www/amazon-rekognition/ # Optional image storage
    save_timestamped_file: True # Set True to save timestamped images, default False
    s3_bucket: my_already_existing_bucket
    always_save_latest_file: True
    source:
      - entity_id: camera.local_file
```

Configuration variables:
- **aws_access_key_id**: Your AWS key ID
- **aws_secret_access_key**: Your AWS key secret
- **region_name**: Your preferred AWS region
- **similarity_threshold**: Optional: default 90 (0‑100)
- **collection_id**: your collection_id name
- **save_file_format**: (Optional, default `jpg`, alternatively `png`) The file format to save images as. `png` generally results in easier to read annotations.
- **save_file_folder**: (Optional) The folder to save processed images to. Note that folder path should be added to [whitelist_external_dirs](https://www.home-assistant.io/docs/configuration/basic/)
- **save_timestamped_file**: (Optional, default `False`, requires `save_file_folder` to be configured) Save the processed image with the time of detection in the filename.
- **s3_bucket**: (Optional, requires `save_timestamped_file` to be True) Backup the timestamped file to an S3 bucket (must already exist)
- **always_save_latest_file**: (Optional, default `False`, requires `save_file_folder` to be configured) Always save the last processed image, even if there were no detections.
- **source**: Must be a camera.


## Add collection and index faces
With AWS cli 
add envs AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY 
```
aws rekognition create-collection \
 --collection-id MyCollection \
 --region eu-west-1
```
than index faces
```
aws rekognition index-faces \
  --region eu-west-1 \
  --collection-id MyCollection \
  --image-bytes fileb://./person1.jpg \
  --external-image-id person1

```

## Events
Every time an image is processed,  event are published. The events can be viewed via the HA UI from `Developer tools -> EVENTS -> :Listen to events`. The events are:

`rekognition.face_recognised`: contains all the data associated with an object.

```<Event rekognition.face_recognised[L]: data:  external_image_id: person1   face_id: xxx-xxx-xxx-xxxx-xxxxxxxxxx   similarity: 98.4   bounding_box:    Width: 0.614870011806488    Height: 0.6904190182685852    Left: 0.20693400502204895    Top: 0.1750749945640564  entity_id: image_processing.rekognition_face_camera_4534_hd_stream timestamp: "2025-05-11T16:45:20.823014+03:00">```


These events can be used to trigger automations, increment counters etc.

## Automation
Example automation to send a  notification when person is a new recognized. Then in `automations.yaml` I have:

```yaml
- id: '3287784389530'
  alias: Rekognition person alert  
  triggers:
    - event_type: rekognition.face_recognised
      event_data:
        external_image_id: person1
      trigger: event
  actions:
    - data:
        message: person1 recognized {{ now().strftime('%H:%M%d.%m.%Y') }}
      action: notify.telegram_notifier
      
```

## Community guides
Here you can find community made guides, tutorials & videos about how to install/use this Amazon Rekognition integration. If you find more links let us know.
* Object Detection in Home Assistant with Amazon Rekognition [video tutorial](https://youtu.be/1G8tnhw2N_Y) and the [full article](https://peyanski.com/amazon-rekognition-in-home-assistant)

