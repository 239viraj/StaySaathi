
import os
from dotenv import load_dotenv
from dbbyte import DBByte

load_dotenv()

DBBYTE_API_KEY = os.getenv("DBBYTE_API_KEY")
DBBYTE_BUCKET = os.getenv("DBBYTE_BUCKET", "staysaathi")

if not DBBYTE_API_KEY:
    raise RuntimeError("DBBYTE_API_KEY is not configured.")

# Initialize DBByte client
db = DBByte(api_key=DBBYTE_API_KEY)


def upload_file(file, object_name):
    """
    Upload a file to DBByte.

    Accepts either:
    - A local file path (string)
    - A Flask FileStorage object

    Returns the DBByte object name on success, otherwise None.
    """

    import mimetypes
    import logging

    try:
        content_type, _ = mimetypes.guess_type(object_name)

        if not content_type:
            content_type = "application/octet-stream"

        # Support Flask FileStorage and local file paths
        if isinstance(file, str):
            with open(file, "rb") as source:
                body = source.read()
        else:
            file.seek(0)
            body = file.read()
            file.seek(0)

        result = db.objects.upload(
            DBBYTE_BUCKET,
            key=object_name,
            body=body,
            content_type=content_type
        )

        print("DBByte upload successful:", result)

        return object_name

    except Exception:
        logging.exception("DBByte upload error")
        return None


def download_file(object_name):
    """
    Download a file from DBByte.

    Returns file bytes on success, otherwise None.
    """

    try:
        result = db.objects.download(
            DBBYTE_BUCKET,
            object_name
        )

        return result["data"]

    except Exception:
        import logging
        logging.exception("DBByte download failed")
        return None


def delete_file(object_name):
    """
    Delete a file from DBByte.

    Returns True on success, otherwise False.
    """

    try:
        db.objects.delete(
            DBBYTE_BUCKET,
            object_name
        )

        return True

    except Exception:
        import logging
        logging.exception("DBByte deletion failed")
        return False
