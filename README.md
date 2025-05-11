# Amazon Rekognition for Home Assistant
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/hacs/integration)

Face recogntion with [Amazon Rekognition](https://aws.amazon.com/rekognition/). The state of the sensor is the number of detected target objects in the image, which match the configured conditions. The default target is `person`, but multiple targets can be listed, in which case the state is the total number of any targets detected. The time that any target object was last detected is available as an attribute. Optionally a region of interest (ROI) can be configured, and only objects with their center (represented by a `x`) will be included in the state count. The ROI will be displayed as a green box, and objects with their center in the ROI have a red box. Rekognition also assigns each image a list of labels, which represent the classes of objects in the image. For example, if the image contained a cat or a dog, the label might be `animal`. Labels are useful if you don't know exactly what object to monitor for. Labels are exposed via the `labels` attribute of the entity.

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
- **save_file_format**: (Optional, default `jpg`, alternatively `png`) The file format to save images as. `png` generally results in easier to read annotations.
- **save_file_folder**: (Optional) The folder to save processed images to. Note that folder path should be added to [whitelist_external_dirs](https://www.home-assistant.io/docs/configuration/basic/)
- **save_timestamped_file**: (Optional, default `False`, requires `save_file_folder` to be configured) Save the processed image with the time of detection in the filename.
- **s3_bucket**: (Optional, requires `save_timestamped_file` to be True) Backup the timestamped file to an S3 bucket (must already exist)
- **always_save_latest_file**: (Optional, default `False`, requires `save_file_folder` to be configured) Always save the last processed image, even if there were no detections.
- **source**: Must be a camera.


## Using the Summary attribute
The Summary attribute will list the count of detected targets. This count can be broken out using a [template](https://www.home-assistant.io/integrations/template/) sensor, for example if you have a target `person`:

```yaml
sensor:
  - platform: template
    sensors:
      rekognition_people:
        friendly_name: "People"
        unit_of_measurement: 'persons'
        value_template: "{{ states.image_processing.rekognition_local_file_1.attributes.summary.person }}"
```

## Events
Every time an image is processed,  event are published. The events can be viewed via the HA UI from `Developer tools -> EVENTS -> :Listen to events`. The events are:

1) `rekognition.face_recognised`: contains all the data associated with an object.

```<Event rrekognition.face_recognised[L]: data:  external_image_id: user   face_id: xxx-xxx-xxx-xxxx-xxxxxxxxxx   similarity: 98.4   bounding_box:    Width: 0.614870011806488    Height: 0.6904190182685852    Left: 0.20693400502204895    Top: 0.1750749945640564  entity_id: image_processing.rekognition_face_camera_4534_hd_stream timestamp: "2025-05-11T16:45:20.823014+03:00">```


These events can be used to trigger automations, increment counters etc.

## Automation
I am using an automation to send a photo notification when there is a new detection. This requires you to setup the [folder_watcher](https://www.home-assistant.io/integrations/folder_watcher/) integration first. Then in `automations.yaml` I have:

```yaml
- id: '3287784389530'
  alias: Rekognition person alert
  trigger:
    event_type: folder_watcher
    platform: event
    event_data:
      event_type: modified
      path: '/config/www/rekognition_my_cam_latest.jpg'
  action:
    service: telegram_bot.send_photo
    data_template:
      caption: Person detected by rekognition
      file: '/config/www/rekognition_my_cam_latest.jpg'
```

## Community guides
Here you can find community made guides, tutorials & videos about how to install/use this Amazon Rekognition integration. If you find more links let us know.
* Object Detection in Home Assistant with Amazon Rekognition [video tutorial](https://youtu.be/1G8tnhw2N_Y) and the [full article](https://peyanski.com/amazon-rekognition-in-home-assistant)

## Development
Currently only the helper functions are tested, using pytest.
* `python3 -m venv venv`
* `source venv/bin/activate`
* `pip install -r requirements-dev.txt`
* `venv/bin/py.test custom_components/amazon_rekognition/tests.py -vv -p no:warnings`

## Video of usage
Checkout this excellent video of usage from [MecaHumArduino](https://www.youtube.com/channel/UCwpIueN8B-42Z8vfxVt0yEQ)

[![](http://img.youtube.com/vi/GCHYBxnZK-E/0.jpg)](http://www.youtube.com/watch?v=GCHYBxnZK-E "")
