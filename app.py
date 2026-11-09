import re
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
import secrets
import hashlib
import hmac
import mimetypes
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler
from storage import upload_file,download_file,delete_file,db,DBBYTE_BUCKET
from sqlalchemy import func
import math
from PIL import Image, UnidentifiedImageError
from io import BytesIO
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from werkzeug.utils import secure_filename
from flask import current_app
from math import radians, sin, cos, sqrt, atan2
from flask import Flask, render_template, request, redirect, url_for, session, flash,abort,send_file,send_from_directory
from flask_wtf.csrf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash, check_password_hash
import os
import uuid
import json
import base64
from urllib.parse import urlencode
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
from flask import session, redirect, url_for, flash

app = Flask(__name__)

# Load environment variables first
load_dotenv()

# Load secret key from .env
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

if not app.config["SECRET_KEY"]:
    raise RuntimeError(
        "SECRET_KEY is missing. Please configure it in your .env file."
    )

# Email configuration for OTP
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_APP_PASSWORD"] = os.getenv("MAIL_APP_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER")
# =========================
# LOGIN RATE LIMITING
# =========================

REDIS_URL = os.environ.get("REDIS_URL")

ENVIRONMENT = os.environ.get(
    "APP_ENV",
    "development"
).lower()

if ENVIRONMENT == "production" and not REDIS_URL:
    raise RuntimeError(
        "REDIS_URL is required in production."
    )

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=REDIS_URL or "memory://"
)
# ==============================
# SESSION SECURITY CONFIGURATION
# ==============================

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Keep False during local HTTP development.
# Change to True when deployed using HTTPS.
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("SESSION_COOKIE_SECURE", "False").lower() == "true"
)

# Session expires when the browser is closed.
app.config["SESSION_PERMANENT"] = False

# Lifetime of permanent sessions
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

# Enable CSRF protection
csrf = CSRFProtect(app)

# =========================
# IMAGE UPLOAD CONFIGURATION
# =========================

# Existing PG image upload folder
app.config["UPLOAD_FOLDER"] = os.path.join(
    app.root_path,
    "static",
    "uploads",
    "pg"
)

# New food menu image upload folder
# app.config["FOOD_MENU_FOLDER"] = os.path.join(
#     app.root_path,
#     "static",
#     "uploads",
#     "food_menus"
# )

# Maximum total size of one upload request: 26 MB
app.config["MAX_CONTENT_LENGTH"] = 26 * 1024 * 1024

# Maximum size of an individual menu photo: 5 MB
MAX_MENU_PHOTO_SIZE = 5 * 1024 * 1024
MAX_PG_IMAGE_SIZE = 5 * 1024 * 1024


# Maximum number of menu photos per business
MAX_MENU_PHOTOS = 5

# Allowed image formats
ALLOWED_IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}
app.config["FOOD_MENU_FOLDER"] = os.path.join(
    app.root_path,
    "static",
    "uploads",
    "food_menus"
)

os.makedirs(app.config["FOOD_MENU_FOLDER"], exist_ok=True)

# Create both folders if they do not exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["FOOD_MENU_FOLDER"], exist_ok=True)

# Individual food menu photo limit remains 5 MB
MAX_MENU_PHOTO_SIZE = 5 * 1024 * 1024

# Maximum number of menu photos per business
MAX_MENU_PHOTOS = 5

ALLOWED_IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}
def allowed_image(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_IMAGE_EXTENSIONS
    )

def validate_image(file_storage):
    try:
        image_data = file_storage.read()

        if not image_data:
            return False

        image = Image.open(BytesIO(image_data))

        if image.format not in {"JPEG", "PNG", "WEBP"}:
            return False

        image.verify()

        # Reopen the image and check its dimensions.
        image = Image.open(BytesIO(image_data))
        width, height = image.size

        if width < 1 or height < 1:
            return False

        if width > 10000 or height > 10000:
            return False

        # Decode the image to catch additional corruption.
        image.load()

        return True

    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError
    ):
        return False

    finally:
        file_storage.seek(0)

def validate_pg_form(form):
    """
    Validate PG details submitted through an HTML form.
    Returns an error message if invalid, otherwise None.
    """

    name = form.get("name", "").strip()
    address = form.get("address", "").strip()
    gender = form.get("gender", "").strip().lower()
    contact = form.get("contact", "").strip()
    description = form.get("description", "").strip()

    # Check PG name
    if not name:
        return "PG name is required."

    if len(name) > 150:
        return "PG name must not exceed 150 characters."

    # Check address
    if not address:
        return "PG address is required."

    if len(address) > 300:
        return "PG address must not exceed 300 characters."

    # Check gender
    if gender not in {"boys", "girls", "unisex"}:
        return "Please select a valid PG category."

    # Check room counts
    try:
        total_rooms = int(form.get("total_rooms", ""))
        available_rooms = int(form.get("available_rooms", ""))
    except (ValueError, TypeError):
        return "Room counts must be valid whole numbers."

    if total_rooms < 1:
        return "Total rooms must be at least 1."

    if available_rooms < 0:
        return "Available rooms cannot be negative."

    if available_rooms > total_rooms:
        return "Available rooms cannot exceed total rooms."
    print("DEBUG: Contact received:", repr(contact))

    # Check contact number
    if not contact:
        return "Please enter a valid contact number."

    # Allow digits, spaces, +, hyphens and parentheses
    if not re.fullmatch(r"[0-9+\-\s()]{10,20}", contact):
        return "Please enter a valid contact number."

    # Count actual digits, excluding formatting characters
    digits_only = re.sub(r"\D", "", contact)

    if not (10 <= len(digits_only) <= 15):
        return "Please enter a valid contact number."

    # Check description length
    if len(description) > 5000:
        return "Description must not exceed 5000 characters."

    return None

# =========================
# DATABASE CONFIGURATION
# =========================

ENVIRONMENT = os.getenv("APP_ENV", "development").lower()

if ENVIRONMENT == "production":

    DATABASE_URL = os.getenv("DATABASE_URL")

    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is missing. Configure Neon PostgreSQL in .env."
        )

    # Use psycopg 3 as the PostgreSQL driver.
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

else:

    # Keep the existing SQLite database during development.
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///pg_finder.db"


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)
# =========================
# DATETIME DISPLAY IN IST
# =========================

@app.template_filter("ist")
def convert_to_ist(value):

    if value is None:
        return "Not available"

    # Database timestamps are stored in UTC.
    utc_time = value.replace(tzinfo=timezone.utc)

    # Convert UTC to Indian Standard Time.
    ist_time = utc_time.astimezone(ZoneInfo("Asia/Kolkata"))

    return ist_time.strftime("%d %b %Y, %I:%M %p")
# =========================
# AUTHORIZATION DECORATORS
# =========================

def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):

        if not session.get("user_id"):
            flash("Please log in to continue.")
            return redirect(url_for("login"))

        return view_function(*args, **kwargs)

    return wrapped_view


def role_required(required_role):
    def decorator(view_function):

        @wraps(view_function)
        def wrapped_view(*args, **kwargs):

            if not session.get("user_id"):
                flash("Please log in to continue.")
                return redirect(url_for("login"))

            if session.get("role") != required_role:
                flash("You are not authorized to access this page.")
                return redirect(url_for("food_finder"))

            return view_function(*args, **kwargs)

        return wrapped_view

    return decorator



# =========================
# USER DATABASE MODEL
# =========================

class User(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)

    email = db.Column(db.String(120), nullable=False)

    phone = db.Column(db.String(15), nullable=False)

    password = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), nullable=False)

    verification_status = db.Column(
        db.String(20),
        nullable=False,
        default="pending"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "email",
            "role",
            name="unique_email_per_role"
        ),
        db.UniqueConstraint(
            "phone",
            "role",
            name="unique_phone_per_role"
        ),
    )

# =========================
# LOGIN OTP MODEL
# =========================

class LoginOTP(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False
    )

    otp_hash = db.Column(
        db.String(64),
        nullable=False
    )

    expires_at = db.Column(
        db.DateTime,
        nullable=False
    )

    attempts = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    used = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )    

#######################pg model###########################

class PG(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(300), nullable=False)

    # Location coordinates
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    gender = db.Column(db.String(20), nullable=False)

    total_rooms = db.Column(db.Integer, nullable=False)
    available_rooms = db.Column(db.Integer, nullable=False)

    wifi = db.Column(db.Boolean, default=False)
    laundry = db.Column(db.Boolean, default=False)
    ac = db.Column(db.Boolean, default=False)
    cctv = db.Column(db.Boolean, default=False)
    power_backup = db.Column(db.Boolean, default=False)

    description = db.Column(db.Text, nullable=True)

    contact = db.Column(db.String(20), nullable=False)
    front_image = db.Column(db.String(300), nullable=True)


        # PG creation and last modification timestamps
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    verification_status = db.Column(
    db.String(20),
    nullable=False,
    default="pending"
)
    __table_args__ = (
    db.CheckConstraint(
        "total_rooms >= 0",
        name="check_pg_total_rooms"
    ),
    db.CheckConstraint(
        "available_rooms >= 0",
        name="check_pg_available_rooms"
    ),
    db.CheckConstraint(
        "available_rooms <= total_rooms",
        name="check_pg_available_rooms_limit"
    ),
)
    # =========================
    # FOOD BUSINESS DATABASE MODEL
    # =========================

class FoodBusiness(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    business_name = db.Column(
        db.String(150),
        nullable=False
    )

    category = db.Column(
        db.String(30),
        nullable=False
    )

    description = db.Column(
        db.Text,
        nullable=True
    )

    phone = db.Column(
        db.String(15),
        nullable=False
    )

    address = db.Column(
        db.String(255),
        nullable=False
    )

    latitude = db.Column(
        db.Float,
        nullable=True
    )

    longitude = db.Column(
        db.Float,
        nullable=True
    )

    opening_hours = db.Column(
        db.String(100),
        nullable=True
    )
    menu_photos=db.Column(
        db.Text, nullable=True
    )

    verification_status = db.Column(
        db.String(20),
        nullable=False,
        default="pending"
    )

    subscription_status = db.Column(
        db.String(20),
        nullable=False,
        default="pending"
    )
    subscription_plan = db.Column(
        db.String(20),
        nullable=True
    )

    subscription_start_date = db.Column(
        db.DateTime,
        nullable=True
    )

    subscription_expiry_date = db.Column(
        db.DateTime,
        nullable=True
    )
    

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    owner = db.relationship(
        "User",
        backref=db.backref("food_businesses", lazy=True)
    )
    

# =========================
# FOOD SUBSCRIPTION PAYMENT REQUESTS
# =========================

class FoodSubscriptionPaymentRequest(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    business_id = db.Column(
        db.Integer,
        db.ForeignKey("food_business.id"),
        nullable=False
    )

    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    plan = db.Column(db.String(20), nullable=False)

    amount = db.Column(db.Integer, nullable=False)

    transaction_reference = db.Column(
        db.String(100),
        nullable=False,
        unique=True
    )

    proof_image = db.Column(db.String(300), nullable=True)

    status = db.Column(
        db.String(20),
        nullable=False,
        default="pending"
    )

    admin_note = db.Column(db.String(500), nullable=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    reviewed_at = db.Column(db.DateTime, nullable=True)

    # ADD THIS PART HERE
    __table_args__ = (
        db.CheckConstraint(
            "amount > 0",
            name="check_payment_amount"
        ),
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="check_payment_status"
        ),
    )

    business = db.relationship(
        "FoodBusiness",
        backref=db.backref("payment_requests", lazy=True)
    )

    owner = db.relationship(
        "User",
        backref=db.backref("food_payment_requests", lazy=True)
    )

FOOD_SUBSCRIPTION_PLANS = {
    "monthly": {"amount": 149, "days": 30, "label": "Monthly"},
    "quarterly": {"amount": 299, "days": 90, "label": "Quarterly"},
    "yearly": {"amount": 799, "days": 365, "label": "Yearly"},
}
FOOD_SUBSCRIPTION_UPI_ID = "8278660320-2@ybl"
# Store payment proof screenshots outside the public static folder
PAYMENT_PROOF_FOLDER = os.path.join(
    app.root_path,
    "private_uploads",
    "payment_proofs"
)

os.makedirs(PAYMENT_PROOF_FOLDER, exist_ok=True)


# =========================
# AUTOMATIC SUBSCRIPTION EXPIRY
# =========================

def update_expired_subscriptions():
    try:
        now = datetime.utcnow()

        expired_businesses = FoodBusiness.query.filter(
            FoodBusiness.subscription_status == "active",
            FoodBusiness.subscription_expiry_date.isnot(None),
            FoodBusiness.subscription_expiry_date <= now
        ).all()

        for business in expired_businesses:
            business.subscription_status = "expired"

        if expired_businesses:
            db.session.commit()

        return len(expired_businesses)

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Failed to update expired food subscriptions."
        )

        raise

# ==========================================
# AUTOMATIC SUBSCRIPTION REMINDER NOTIFICATIONS
# ==========================================

def send_subscription_reminders():

    with app.app_context():

        try:
            now = datetime.utcnow()
            today = now.date()

            # First, mark expired active subscriptions as expired.
            update_expired_subscriptions()

            # Get businesses with an expiry date.
            businesses = FoodBusiness.query.filter(
                FoodBusiness.subscription_expiry_date.isnot(None),
                FoodBusiness.subscription_status.in_(
                    ["active", "expired"]
                )
            ).all()

            for business in businesses:

                expiry_date = business.subscription_expiry_date.date()
                days_remaining = (expiry_date - today).days

                title = None
                message = None

                # ----------------------------------
                # 7-DAY REMINDER
                # ----------------------------------
                if (
                    business.subscription_status == "active"
                    and days_remaining == 7
                ):
                    title = "Subscription expires in 7 days"

                    message = (
                        f"Your subscription for {business.business_name} "
                        f"expires on {expiry_date.strftime('%d-%m-%Y')}. "
                        "Please renew it to maintain your Food Finder visibility."
                    )

                # ----------------------------------
                # 1-DAY REMINDER
                # ----------------------------------
                elif (
                    business.subscription_status == "active"
                    and days_remaining == 1
                ):
                    title = "Subscription expires tomorrow"

                    message = (
                        f"Your subscription for {business.business_name} "
                        f"expires tomorrow, "
                        f"{expiry_date.strftime('%d-%m-%Y')}. "
                        "Please renew it to maintain your Food Finder visibility."
                    )

                # ----------------------------------
                # EXPIRED SUBSCRIPTION
                # ----------------------------------
                elif (
                    business.subscription_status == "expired"
                    and days_remaining <= 0
                ):
                    title = "Subscription expired"

                    message = (
                        f"Your subscription for {business.business_name} "
                        f"expired on {expiry_date.strftime('%d-%m-%Y')}. "
                        "Please renew it to restore your Food Finder visibility."
                    )

                # No reminder needed.
                if title is None:
                    continue

                # ----------------------------------
                # PREVENT DUPLICATE NOTIFICATIONS
                # ----------------------------------
                existing_notification = Notification.query.filter_by(
                    user_id=business.owner_id,
                    title=title,
                    message=message,
                    notification_type="subscription_reminder"
                ).first()

                if existing_notification:
                    continue

                # ----------------------------------
                # CREATE NOTIFICATION
                # ----------------------------------
                notification = Notification(
                    user_id=business.owner_id,
                    title=title,
                    message=message,
                    notification_type="subscription_reminder",
                    is_read=False
                )

                db.session.add(notification)

            db.session.commit()

            app.logger.info(
                "Subscription reminder job completed successfully."
            )

        except Exception:
            db.session.rollback()

            app.logger.exception(
                "Failed to generate subscription reminder notifications."
            )

        finally:
            db.session.remove()


# =========================
# FOOD BUSINESS REGISTRATION
# =========================

@app.route("/register-food-business", methods=["GET", "POST"])
def register_food_business():

    # Only food business owners can register food businesses.
    if (
        "user_id" not in session
        or session.get("role") != "food_owner"
    ):
        flash("Please log in as a food business owner to register.")
        return redirect(url_for("food_owner_login"))

    if request.method == "GET":
        return render_template("register_food_business.html")

    # Read form fields.
    business_name = request.form.get("business_name", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    phone = request.form.get("phone", "").strip()
    address = request.form.get("address", "").strip()
    opening_hours = request.form.get("opening_hours", "").strip()

    latitude_text = request.form.get("latitude", "").strip()
    longitude_text = request.form.get("longitude", "").strip()

    # Validate required fields.
    if not all([business_name, category, phone, address]):
        flash("Please fill in all required fields.")
        return render_template("register_food_business.html")

    allowed_categories = {
        "dhaba",
        "food_stall",
        "restaurant",
        "tiffin_service"
    }
    category = category.strip().lower()

    if category not in allowed_categories:
        flash("Please select a valid business category.")
        return render_template("register_food_business.html")

    if (
        len(business_name) > 150
        or len(phone) > 15
        or len(address) > 255
        or len(description) > 2000
        or len(opening_hours) > 100
    ):
        flash("One or more fields exceed the allowed length.")
        return render_template("register_food_business.html")

    # Validate coordinates.
    try:
        latitude = float(latitude_text) if latitude_text else None
        longitude = float(longitude_text) if longitude_text else None
    except ValueError:
        flash("Please enter valid latitude and longitude values.")
        return render_template("register_food_business.html")

    print("========== FOOD BUSINESS LOCATION ==========")
    print("Business Name:", business_name)
    print("Address:", address)
    print("Latitude:", latitude)
    print("Longitude:", longitude)
    print("============================================")

    if latitude is not None and (
        not math.isfinite(latitude) or not -90 <= latitude <= 90
    ):
        flash("Latitude must be between -90 and 90.")
        return render_template("register_food_business.html")

    if longitude is not None and (
        not math.isfinite(longitude) or not -180 <= longitude <= 180
    ):
        flash("Longitude must be between -180 and 180.")
        return render_template("register_food_business.html")

    if (latitude is None) != (longitude is None):
        flash("Please provide both latitude and longitude.")
        return render_template("register_food_business.html")

    photos = [
        photo for photo in request.files.getlist("menu_photos")
        if photo and photo.filename.strip()

    ]
    print("Number of menu photos received:", len(photos))
    print("Received filenames:", [photo.filename for photo in photos])
    if len(photos) > MAX_MENU_PHOTOS:
        flash("Please upload between 1 and 5 menu photos.")
        return render_template("register_food_business.html")
    # print("Number of menu photos received:", len(photos))
    # print("Received filenames:", [photo.filename for photo in photos])

    validated_photos = []

    # Validate every image before saving any of them.
    for photo in photos:

        if not photo or not photo.filename:
            flash("One of the selected menu photos is missing.")
            return render_template("register_food_business.html")

        original_name = secure_filename(photo.filename)

        if not original_name or "." not in original_name:
            flash("One of the uploaded filenames is invalid.")
            return render_template("register_food_business.html")

        extension = original_name.rsplit(".", 1)[1].lower()

        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            flash("Menu photos must be JPG, PNG, or WebP.")
            return render_template("register_food_business.html")

        # Read at most 5 MB plus one byte to detect oversized files.
        photo.stream.seek(0)
        image_bytes = photo.stream.read(MAX_MENU_PHOTO_SIZE + 1)
        photo.stream.seek(0)

        if not image_bytes:
            flash("Empty menu photos are not allowed.")
            return render_template("register_food_business.html")

        if len(image_bytes) > MAX_MENU_PHOTO_SIZE:
            flash("Each menu photo must be 5 MB or smaller.")
            return render_template("register_food_business.html")

        try:
            import io

            with Image.open(io.BytesIO(image_bytes)) as image:
                actual_format = image.format
                image.verify()

            allowed_formats = {
                "jpg": {"JPEG"},
                "jpeg": {"JPEG"},
                "png": {"PNG"},
                "webp": {"WEBP"}
            }

            if actual_format not in allowed_formats[extension]:
                flash("A menu photo's file extension does not match its content.")
                return render_template("register_food_business.html")

            # Reopen and fully decode the image.
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.load()

                if image.width < 1 or image.height < 1:
                    flash("An uploaded menu photo has invalid dimensions.")
                    return render_template("register_food_business.html")

        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            flash("One of the uploaded files is not a valid image.")
            return render_template("register_food_business.html")

        validated_photos.append((extension, image_bytes))

    # Prepare unique filenames. Store only relative paths in the database.
    # =========================
    # UPLOAD MENU PHOTOS TO DBBYTE
    # =========================

    uploaded_objects = []
    photo_paths = []

    try:
        for extension, image_bytes in validated_photos:

            filename = f"{uuid.uuid4().hex}.{extension}"

            object_name = f"food-menus/{filename}"

            content_types = {
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "png": "image/png",
                "webp": "image/webp"
            }

            # Upload image bytes to DBByte
            result = db.objects.upload(
                DBBYTE_BUCKET,
                key=object_name,
                body=image_bytes,
                content_type=content_types[extension]
            )

            if not result:
                raise RuntimeError(
                    "Failed to upload a menu photo to DBByte."
                )

            uploaded_objects.append(object_name)

            # Store DBByte object name in database
            photo_paths.append(object_name)

        food_business = FoodBusiness(
            owner_id=session["user_id"],
            business_name=business_name,
            category=category,
            description=description,
            phone=phone,
            address=address,
            latitude=latitude,
            longitude=longitude,
            opening_hours=opening_hours,
            menu_photos=json.dumps(photo_paths),
            verification_status="pending",
            subscription_status="pending"
        )

        db.session.add(food_business)
        db.session.commit()

    except Exception as e:
        db.session.rollback()

        # Remove files if registration fails.
        # Delete uploaded DBByte objects if registration fails.
        for object_name in uploaded_objects:
            try:
                delete_file(object_name)
            except Exception:
                app.logger.exception(
                    "Could not delete uploaded menu photo: %s",
                    object_name
                )

        # Print the actual error in the terminal.
        app.logger.exception("Failed to register food business")

        # Show a generic message to the user.
        flash("Registration failed. Please check the terminal for details.")

        return render_template("register_food_business.html")
    flash(
        "Food business registered successfully!"
        "Your listing is awaiting verification and subscription activation."
    )
    return redirect(url_for("food_owner_dashboard"))

##############food_finder####################

@app.route("/food-finder")
def food_finder():

    update_expired_subscriptions()

    category = request.args.get(
        "category", ""
    ).strip().lower()

    location = request.args.get(
        "location", ""
    ).strip()

    # User's current coordinates from browser
    user_lat = request.args.get("latitude", type=float)
    user_lon = request.args.get("longitude", type=float)

    # Optional search radius in kilometers
    radius = request.args.get("radius", type=float)

    if radius not in (2, 5, 10):
        radius = None

    # Only show verified businesses with active subscriptions
    now = datetime.utcnow()

    query = FoodBusiness.query.filter(
        FoodBusiness.verification_status == "verified",
        FoodBusiness.subscription_status == "active",
        FoodBusiness.subscription_expiry_date > now
    )

    # Filter by category
    allowed_categories = {
        "dhaba",
        "restaurant",
        "food_stall",
        "tiffin_service"
    }

    if category in allowed_categories:
        query = query.filter(
            db.func.lower(FoodBusiness.category) == category
        )

    # Filter by address
    if location:
        query = query.filter(
            FoodBusiness.address.ilike(f"%{location}%")
        )

    businesses = query.order_by(
        FoodBusiness.created_at.desc()
    ).all()

    # Prepare menu photos and distance information
    for business in businesses:

        # Menu photos
        # Menu photos
        try:
            photo_paths = json.loads(
                business.menu_photos or "[]"
            )

            if not isinstance(photo_paths, list):
                photo_paths = []

            business.display_menu_photos = [
                path for path in photo_paths
                if (
                    isinstance(path, str)
                    and (
                        path.startswith("food-menus/")
                        or path.startswith("uploads/food_menus/")
                    )
                    and ".." not in path.split("/")
                    and "\\" not in path
                )
            ]

        except (json.JSONDecodeError, TypeError):
            business.display_menu_photos = []
        # Distance
        business.distance_km = None

        if (
            user_lat is not None
            and user_lon is not None
            and business.latitude is not None
            and business.longitude is not None
        ):
            business.distance_km = calculate_distance(
                user_lat,
                user_lon,
                business.latitude,
                business.longitude
            )

    # When coordinates are provided, sort by distance
    if user_lat is not None and user_lon is not None:

        businesses.sort(
            key=lambda business: (
                business.distance_km is None,
                business.distance_km
                if business.distance_km is not None
                else float("inf")
            )
        )

        # Apply radius filter
        if radius is not None:
            businesses = [
                business for business in businesses
                if (
                    business.distance_km is not None
                    and business.distance_km <= radius
                )
            ]

    return render_template(
        "food_finder.html",
        businesses=businesses,
        selected_category=category,
        search_location=location,
        user_latitude=user_lat,
        user_longitude=user_lon,
        selected_radius=radius
    )


# =========================
# SAVED PG DATABASE MODEL
# =========================

class SavedPG(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    pg_id = db.Column(
        db.Integer,
        db.ForeignKey("pg.id"),
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "student_id",
            "pg_id",
            name="unique_student_pg_saved"
        ),
    )

####################review####################################    
class Review(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    pg_id = db.Column(
        db.Integer,
        db.ForeignKey("pg.id"),
        nullable=False
    )

    # Overall rating: 1 to 5
    rating = db.Column(
        db.Integer,
        nullable=False
    )

    # Individual ratings
    cleanliness = db.Column(
        db.Integer,
        nullable=True
    )

    safety = db.Column(
        db.Integer,
        nullable=True
    )

    location_rating = db.Column(
        db.Integer,
        nullable=True
    )

    facilities_rating = db.Column(
        db.Integer,
        nullable=True
    )

    comment = db.Column(
        db.Text,
        nullable=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # One student can review a particular PG only once
    __table_args__ = (
        db.UniqueConstraint(
            "student_id",
            "pg_id",
            name="unique_student_pg_review"
        ),

        db.CheckConstraint(
            "rating BETWEEN 1 AND 5",
            name="check_review_rating"
        ),

        db.CheckConstraint(
            "cleanliness IS NULL OR cleanliness BETWEEN 1 AND 5",
            name="check_review_cleanliness"
        ),

        db.CheckConstraint(
            "safety IS NULL OR safety BETWEEN 1 AND 5",
            name="check_review_safety"
        ),

        db.CheckConstraint(
            "location_rating IS NULL OR location_rating BETWEEN 1 AND 5",
            name="check_review_location"
        ),

        db.CheckConstraint(
            "facilities_rating IS NULL OR facilities_rating BETWEEN 1 AND 5",
            name="check_review_facilities"
        ),
    )
    # =========================================
    # PG REPORT MODEL
    # =========================================

class Report(db.Model):

        id = db.Column(
            db.Integer,
            primary_key=True
        )

        student_id = db.Column(
            db.Integer,
            db.ForeignKey("user.id"),
            nullable=False
        )

        pg_id = db.Column(
            db.Integer,
            db.ForeignKey("pg.id"),
            nullable=False
        )

        reason = db.Column(
            db.String(100),
            nullable=False
        )

        description = db.Column(
            db.Text,
            nullable=True
        )

        status = db.Column(
            db.String(20),
            nullable=False,
            default="pending"
        )

        admin_note = db.Column(
            db.Text,
            nullable=True
        )

        created_at = db.Column(
            db.DateTime,
            default=datetime.utcnow
        )

        updated_at = db.Column(
            db.DateTime,
            default=datetime.utcnow,
            onupdate=datetime.utcnow
        )


# =========================================
# NOTIFICATION MODEL
# =========================================

class Notification(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    title = db.Column(
        db.String(200),
        nullable=False
    )

    message = db.Column(
        db.Text,
        nullable=False
    )

    notification_type = db.Column(
        db.String(50),
        nullable=False,
        default="general"
    )

    is_read = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

import math


def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two coordinates in kilometers.
    Uses the Haversine formula.
    """

    earth_radius = 6371.0

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return earth_radius * c    


# =========================
# HOME PAGE
# =========================

@app.route("/")
def home():
    return render_template("index.html")


# =========================
# FIND PG
# =========================

@app.route("/find-pg")
def find_pg():

    location = request.args.get(
        "location",
        ""
    ).strip()

    gender = request.args.get(
        "gender",
        ""
    ).strip()

    available_only = (
        request.args.get("available_only") == "on"
    )

    sort_by = request.args.get(
        "sort_by",
        "relevance"
    )

    user_latitude = request.args.get(
        "latitude",
        type=float
    )

    user_longitude = request.args.get(
        "longitude",
        type=float
    )

    # Validate user coordinates
    if user_latitude is not None and not -90 <= user_latitude <= 90:
        user_latitude = None

    if user_longitude is not None and not -180 <= user_longitude <= 180:
        user_longitude = None

    radius = request.args.get(
        "radius",
        "any"
    )

    wifi = request.args.get("wifi") == "on"
    laundry = request.args.get("laundry") == "on"
    ac = request.args.get("ac") == "on"
    cctv = request.args.get("cctv") == "on"

    power_backup = (
        request.args.get("power_backup") == "on"
    )

    # =========================
    # BUILD DATABASE QUERY
    # =========================

    query = PG.query.join(
        User,
        PG.owner_id == User.id
    ).filter(
        PG.verification_status == "verified",
        User.verification_status == "verified"
    )

    if location:
        query = query.filter(
            PG.address.ilike(f"%{location}%")
        )

    if gender and gender.lower() != "any":
        query = query.filter(
            PG.gender.ilike(gender)
        )

    if available_only:
        query = query.filter(
            PG.available_rooms > 0
        )

    if wifi:
        query = query.filter(PG.wifi == True)

    if laundry:
        query = query.filter(PG.laundry == True)

    if ac:
        query = query.filter(PG.ac == True)

    if cctv:
        query = query.filter(PG.cctv == True)

    if power_backup:
        query = query.filter(PG.power_backup == True)

    # =========================
    # FETCH PG LISTINGS
    # =========================

    try:
        pgs = query.all()

    except SQLAlchemyError:

        db.session.rollback()

        app.logger.exception(
            "Database error while searching PG listings."
        )

        flash(
            "Unable to load PG listings right now. Please try again.",
            "danger"
        )

        return render_template(
            "find_pg.html",
            pgs=[],
            map_pgs=[],
            location=location,
            gender=gender,
            available_only=available_only,
            sort_by=sort_by,
            radius=radius,
            user_latitude=user_latitude,
            user_longitude=user_longitude,
            wifi=wifi,
            laundry=laundry,
            ac=ac,
            cctv=cctv,
            power_backup=power_backup
        )

    # =========================
    # FETCH REVIEW STATISTICS
    # =========================

    review_stats = {}

    try:

        if pgs:

            stats = db.session.query(
                Review.pg_id,
                func.count(Review.id),
                func.avg(Review.rating)
            ).filter(
                Review.pg_id.in_([pg.id for pg in pgs])
            ).group_by(
                Review.pg_id
            ).all()

            review_stats = {
                pg_id: {
                    "review_count": count,
                    "average_rating": round(float(avg or 0), 1)
                }
                for pg_id, count, avg in stats
            }

    except SQLAlchemyError:

        db.session.rollback()

        app.logger.exception(
            "Database error while loading PG review statistics."
        )

        flash(
            "Unable to load review statistics. Please try again.",
            "danger"
        )

        return render_template(
            "find_pg.html",
            pgs=[],
            map_pgs=[],
            location=location,
            gender=gender,
            available_only=available_only,
            sort_by=sort_by,
            radius=radius,
            user_latitude=user_latitude,
            user_longitude=user_longitude,
            wifi=wifi,
            laundry=laundry,
            ac=ac,
            cctv=cctv,
            power_backup=power_backup
        )

    # =========================
    # RADIUS
    # =========================

    selected_radius = None

    if radius != "any":

        try:
            selected_radius = float(radius)

        except ValueError:
            selected_radius = None

    # =========================
    # RESULTS
    # =========================

    results = []
    map_pgs = []

    for pg in pgs:

        distance = None

        # =========================
        # DISTANCE
        # =========================

        if (
            user_latitude is not None
            and user_longitude is not None
            and pg.latitude is not None
            and pg.longitude is not None
        ):

            R = 6371.0

            lat1 = radians(user_latitude)
            lon1 = radians(user_longitude)

            lat2 = radians(pg.latitude)
            lon2 = radians(pg.longitude)

            dlat = lat2 - lat1
            dlon = lon2 - lon1

            a = (
                sin(dlat / 2) ** 2
                +
                cos(lat1)
                * cos(lat2)
                * sin(dlon / 2) ** 2
            )

            a = max(0.0, min(1.0, a))

            c = 2 * atan2(
                sqrt(a),
                sqrt(1 - a)
            )

            distance = round(
                R * c,
                2
            )

        # =========================
        # RADIUS FILTER
        # =========================

        if (
            selected_radius is not None
            and distance is not None
            and distance > selected_radius
        ):
            continue

        # =========================
        # REVIEWS
        # =========================

        pg_stats = review_stats.get(
            pg.id,
            {
                "review_count": 0,
                "average_rating": 0
            }
        )

        review_count = pg_stats["review_count"]

        average_rating = pg_stats["average_rating"]

        # =========================
        # ADD RESULT
        # =========================

        results.append({

            "pg": pg,

            "distance": distance,

            "review_count": review_count,

            "average_rating": average_rating

        })

        # =========================
        # MAP DATA
        # =========================

        if (
            pg.latitude is not None
            and pg.longitude is not None
        ):

            map_pgs.append({

                "id": pg.id,

                "name": pg.name,

                "latitude": pg.latitude,

                "longitude": pg.longitude,

                "address": pg.address,

                "gender": pg.gender,

                "available_rooms": pg.available_rooms,

                "average_rating": average_rating,

                "review_count": review_count,

                "distance": distance

            })

    # =========================
    # SORT
    # =========================

    if sort_by == "nearest":

        results.sort(
            key=lambda item: (
                item["distance"] is None,
                item["distance"]
                if item["distance"] is not None
                else float("inf")
            )
        )

        map_pgs.sort(
            key=lambda item: (
                item["distance"] is None,
                item["distance"]
                if item["distance"] is not None
                else float("inf")
            )
        )

    # =========================
    # RENDER PAGE
    # =========================

    return render_template(
        "find_pg.html",
        pgs=results,
        map_pgs=map_pgs,
        location=location,
        gender=gender,
        available_only=available_only,
        sort_by=sort_by,
        radius=radius,
        user_latitude=user_latitude,
        user_longitude=user_longitude,
        wifi=wifi,
        laundry=laundry,
        ac=ac,
        cctv=cctv,
        power_backup=power_backup
    )

########compare pg#################

@app.route("/compare-pgs")
def compare_pgs():

    # =========================
    # STUDENT AUTHENTICATION
    # =========================

    if (
        "user_id" not in session
        or session.get("role") != "student"
    ):
        return redirect(
            url_for("student_login")
        )

    # =========================
    # GET SELECTED PG IDS
    # =========================

    ids_string = request.args.get(
        "ids",
        ""
    ).strip()

    if not ids_string:

        flash(
            "Please select PGs to compare.",
            "warning"
        )

        return redirect(
            url_for("find_pg")
        )

    # =========================
    # VALIDATE PG IDS
    # =========================

    try:

        pg_ids = [
            int(pg_id.strip())
            for pg_id in ids_string.split(",")
            if pg_id.strip()
        ]

    except ValueError:

        flash(
            "Invalid PG selection.",
            "danger"
        )

        return redirect(
            url_for("find_pg")
        )

    # Reject zero and negative IDs
    if any(pg_id <= 0 for pg_id in pg_ids):

        flash(
            "Invalid PG selection.",
            "danger"
        )

        return redirect(
            url_for("find_pg")
        )

    # Remove duplicate IDs
    pg_ids = list(
        dict.fromkeys(pg_ids)
    )

    # Maximum 3 PGs
    pg_ids = pg_ids[:3]

    # At least 2 PGs required
    if len(pg_ids) < 2:

        flash(
            "Please select at least 2 PGs to compare.",
            "warning"
        )

        return redirect(
            url_for("find_pg")
        )

    # =========================
    # FETCH VERIFIED PGs
    # =========================

    try:

        pgs = PG.query.join(
            User,
            PG.owner_id == User.id
        ).filter(
            PG.id.in_(pg_ids),
            PG.verification_status == "verified",
            User.role == "owner",
            User.verification_status == "verified"
        ).all()

    except SQLAlchemyError:

        db.session.rollback()

        app.logger.exception(
            "Database error while fetching PGs for comparison."
        )

        flash(
            "Unable to compare PGs right now. Please try again.",
            "danger"
        )

        return redirect(
            url_for("find_pg")
        )

    # Ensure all selected PGs are available
    if len(pgs) != len(pg_ids):

        flash(
            "Some selected PGs are unavailable or not verified.",
            "warning"
        )

        return redirect(
            url_for("find_pg")
        )

    # =========================
    # FETCH REVIEW STATISTICS
    # =========================

    review_stats = {}

    try:

        stats = db.session.query(
            Review.pg_id,
            func.count(Review.id),
            func.avg(Review.rating)
        ).filter(
            Review.pg_id.in_(pg_ids)
        ).group_by(
            Review.pg_id
        ).all()

        review_stats = {

            pg_id: {
                "review_count": count,
                "average_rating": round(
                    float(avg or 0),
                    1
                )
            }

            for pg_id, count, avg in stats
        }

    except SQLAlchemyError:

        db.session.rollback()

        app.logger.exception(
            "Database error while loading comparison review statistics."
        )

        flash(
            "Unable to load PG ratings right now. Please try again.",
            "danger"
        )

        return redirect(
            url_for("find_pg")
        )

    # =========================
    # PREPARE COMPARISON DATA
    # =========================

    pg_lookup = {
        pg.id: pg
        for pg in pgs
    }

    comparison_pgs = []

    for pg_id in pg_ids:

        pg = pg_lookup[pg_id]

        pg_stats = review_stats.get(
            pg.id,
            {
                "review_count": 0,
                "average_rating": 0
            }
        )

        comparison_pgs.append({

            "pg": pg,

            "average_rating": pg_stats["average_rating"],

            "review_count": pg_stats["review_count"]

        })

    # =========================
    # RENDER COMPARISON PAGE
    # =========================

    return render_template(
        "compare_pgs.html",
        pgs=comparison_pgs
    )

####################pg images################

@app.route("/pg-image/<path:object_name>")
def pg_image(object_name):

    # New images stored in DBByte
    if object_name.startswith("pg-images/"):

        image_data = download_file(object_name)

        if not image_data:
            abort(404)

        content_type = mimetypes.guess_type(object_name)[0]

        return send_file(
            BytesIO(image_data),
            mimetype=content_type or "application/octet-stream",
            max_age=3600
        )

    # Old images stored locally
    if "/" not in object_name and "\\" not in object_name:

        return send_from_directory(
            app.config["UPLOAD_FOLDER"],
            object_name
        )

    abort(404)

########food menu images#####################


@app.route("/food-menu-image/<path:object_name>")
def food_menu_image(object_name):

    # 1. Handle images stored in DBByte
    if object_name.startswith("food-menus/"):

        image_data = download_file(object_name)

        if not image_data:
            abort(404)

        content_type = mimetypes.guess_type(object_name)[0]

        return send_file(
            BytesIO(image_data),
            mimetype=content_type or "application/octet-stream",
            max_age=3600
        )

    # 2. Handle old images stored locally
    if object_name.startswith("uploads/food_menus/"):

        filename = object_name.replace("uploads/food_menus/", "", 1)

        # Prevent unsafe filenames
        if (
            not filename
            or "/" in filename
            or "\\" in filename
            or ".." in filename
        ):
            abort(404)

        return send_from_directory(
            app.config["FOOD_MENU_FOLDER"],
            filename
        )

    # Reject all other paths
    abort(404)

    
################### opt to gmail function ###########################
def send_otp_email(recipient_email, otp):
    message = EmailMessage()

    message["Subject"] = "Your PG Finder Login OTP"
    message["From"] = app.config["MAIL_DEFAULT_SENDER"]
    message["To"] = recipient_email

    message.set_content(
        f"""
Hello,

Your PG Finder login OTP is: {otp}

This OTP is valid for 5 minutes.

Do not share this OTP with anyone.

If you did not request this OTP, you can ignore this email.

Regards,
PG Finder Team
"""
    )

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
        server.starttls()

        server.login(
            app.config["MAIL_USERNAME"],
            app.config["MAIL_APP_PASSWORD"]
        )

        server.send_message(message)
# =========================
# ABOUT
# =========================

@app.route("/about")
def about():
    return render_template("about.html")


# =========================
# LOGIN SELECTION
# =========================

@app.route("/login")
def login():
    return render_template("login.html")


# =========================
# REGISTRATION
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "").strip().lower()

        # 1. Validate name
        if not name or len(name) > 100:
            flash("Name is required and must not exceed 100 characters.")
            return redirect(url_for("register"))

        # 2. Validate email
        email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

        if len(email) > 254 or not re.fullmatch(email_pattern, email):
            flash("Please enter a valid email address.")
            return redirect(url_for("register"))

        # 3. Validate phone number
        digits_only = re.sub(r"\D", "", phone)

        if not re.fullmatch(r"[0-9+\-\s()]{10,20}", phone) or not (
            10 <= len(digits_only) <= 15
        ):
            flash("Please enter a valid phone number.")
            return redirect(url_for("register"))

        # 4. Validate password
        if len(password) < 8 or len(password) > 128:
            flash("Password must be between 8 and 128 characters.")
            return redirect(url_for("register"))

        # 5. Validate role
        if role not in {"student", "owner","food_owner"}:
            flash("Please select a valid account type.")
            return redirect(url_for("register"))

        # 6. Check for an existing email
        existing_email = User.query.filter(
            func.lower(User.email) == email.lower(),
            User.role == role
            ).first()

        if existing_email:
            flash("Email already registered for this account type.")
            return redirect(url_for("register"))

        # 7. Check for an existing phone number
        existing_phone = User.query.filter(
            User.phone == phone,
            User.role == role
            ).first()

        if existing_phone:
            flash("Phone number already registered for this account type.")
            return redirect(url_for("register"))

        # 8. Hash password
        hashed_password = generate_password_hash(password)

        # 9. Create account
        new_user = User(
            name=name,
            email=email,
            phone=phone,
            password=hashed_password,
            role=role
        )

        try:
            db.session.add(new_user)
            db.session.commit()

        except Exception:
            db.session.rollback()
            app.logger.exception("Registration failed")
            flash("Registration could not be completed. Please try again.")
            return redirect(url_for("register"))

        flash("Registration successful! Please login.")
        return redirect(url_for("login"))

    return render_template("register.html")
# =========================
# STUDENT LOGIN
# =========================

@app.route("/student_login", methods=["GET", "POST"])
@limiter.limit("5 per minute" , methods=["POST"])
def student_login():

    if request.method == "POST":

        # Get form data safely
        login_method = request.form.get(
            "login_method", ""
        ).strip().lower()

        identifier = request.form.get(
            "identifier", ""
        ).strip()

        password = request.form.get("password", "")

        # Validate login method
        if login_method not in {"email", "phone"}:
            flash("Invalid email/phone or password.")
            return render_template("student_login.html")

        # Check that required fields are provided
        if not identifier or not password:
            flash("Please enter your login details.")
            return render_template("student_login.html")

        # Find student by email or phone
        if login_method == "email":

            user = User.query.filter_by(
                email=identifier.lower(),
                role="student"
            ).first()

        else:

            user = User.query.filter_by(
                phone=identifier,
                role="student"
            ).first()

        # Verify password
        if user and check_password_hash(
            user.password, password
        ):

            # Clear old session data before login
            session.clear()

            # Create authenticated session
            session["user_id"] = user.id
            session["role"] = user.role
            session["name"] = user.name

            # Redirect to student dashboard
            return redirect(
                url_for("student_dashboard")
            )

        # Generic error message
        flash("Invalid email/phone or password.")

    return render_template(
        "student_login.html",
        otp_role="student"
    )

# =========================
# OWNER LOGIN
# =========================

@app.route("/owner_login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def owner_login():

    if request.method == "POST":

        # Get form data safely
        login_method = request.form.get(
            "login_method", "phone"
        ).strip().lower()

        identifier = request.form.get(
            "identifier", ""
        ).strip()

        password = request.form.get("password", "")

        # Validate login method
        if login_method not in {"email", "phone"}:
            flash("Invalid email/phone or password.")
            return render_template("owner_login.html")

        # Check that required fields are provided
        if not identifier or not password:
            flash("Please enter your login details.")
            return render_template("owner_login.html")

        # Find owner by email or phone
        if login_method == "email":

            user = User.query.filter_by(
                email=identifier.lower(),
                role="owner"
            ).first()

        else:

            user = User.query.filter_by(
                phone=identifier,
                role="owner"
            ).first()

        # Verify password
        if user and check_password_hash(
            user.password, password
        ):

            # Clear old session data before login
            session.clear()

            # Create authenticated session
            session["user_id"] = user.id
            session["role"] = user.role
            session["name"] = user.name

            # Redirect to owner dashboard
            return redirect(
                url_for("owner_dashboard")
            )

        # Generic error message
        flash("Invalid email/phone or password.")

    return render_template(
        "owner_login.html",
        otp_role="owner"
    )


# =========================
# FOOD OWNER LOGIN
# =========================

@app.route("/food-owner-login", methods=["GET", "POST"])
@limiter.limit("5 per minute",methods=["POST"])
def food_owner_login():

    if request.method == "POST":

        # Get login details
        login_method = request.form.get("login_method", "phone")
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        # Find food business owner using email or phone
        if login_method == "phone":
            user = User.query.filter_by(
                phone=identifier,
                role="food_owner"
            ).first()

        elif login_method == "email":
            user = User.query.filter_by(
                email=identifier,
                role="food_owner"
            ).first()

        else:
            user = None

        # Verify credentials
        if user and check_password_hash(user.password, password):

            session.clear()

            session["user_id"] = user.id
            session["name"] = user.name
            session["role"] = user.role

            flash("Login successful!", "success")

            return redirect(url_for("food_owner_dashboard"))

        flash("Invalid phone number/email or password.", "danger")

    return render_template(
        "food_owner_login.html",
        otp_role = "food_owner"
    )
                           


# =========================
# OTP LOGIN: REQUEST OTP
# =========================

@app.route("/login-otp/request", methods=["POST"])
@limiter.limit("5 per 10 minutes", methods=["POST"])
def request_login_otp():

    role = request.form.get("role", "").strip().lower()
    login_method = request.form.get("login_method", "").strip().lower()
    identifier = request.form.get("identifier", "").strip()

    valid_roles = {"student", "owner", "food_owner"}

    # Validate form data
    if (
        role not in valid_roles
        or login_method not in {"email", "phone"}
        or not identifier
    ):
        flash("Please enter valid login details.", "danger")
        return redirect(url_for("otp_login"))

    # SMS OTP is not implemented yet
    if login_method == "phone":
        flash(
            "Phone OTP login is not available yet. Please select email.",
            "warning"
        )
        return redirect(url_for("otp_login"))

    identifier = identifier.lower()

    try:
        user = User.query.filter_by(
            email=identifier,
            role=role
        ).first()

        # Do not reveal whether an account exists
        if not user:
            flash(
                "If your account exists, an OTP email can be sent. "
                "Check the registered email address.",
                "info"
            )
            return redirect(url_for("otp_login"))

        # Invalidate previous unused OTP challenges
        LoginOTP.query.filter_by(
            user_id=user.id,
            role=role,
            used=False
        ).update({"used": True})

        # Generate secure six-digit OTP
        otp = f"{secrets.randbelow(1000000):06d}"

        # Hash OTP before storing
        otp_hash = hashlib.sha256(
            otp.encode("utf-8")
        ).hexdigest()

        challenge = LoginOTP(
            user_id=user.id,
            role=role,
            otp_hash=otp_hash,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            attempts=0,
            used=False
        )

        db.session.add(challenge)
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while creating login OTP challenge."
        )

        flash(
            "Unable to process your login request. Please try again.",
            "danger"
        )
        return redirect(url_for("otp_login"))

    # Send OTP email
    try:
        send_otp_email(user.email, otp)

    except Exception:
        app.logger.exception("Failed to send login OTP email")

        try:
            challenge.used = True
            db.session.commit()

        except SQLAlchemyError:
            db.session.rollback()

            app.logger.exception(
                "Failed to invalidate OTP after email sending failure."
            )

        session.pop("login_otp_challenge_id", None)

        flash(
            "Unable to send the OTP email. Please try again later.",
            "danger"
        )
        return redirect(url_for("otp_login"))

    # Store challenge ID only after email succeeds
    session["login_otp_challenge_id"] = challenge.id

    flash(
        "If your account exists, an OTP email has been sent. "
        "Check your inbox and spam folder.",
        "success"
    )

    return redirect(url_for("otp_login"))
# =========================
# OTP LOGIN: VERIFY OTP
# =========================

@app.route("/login-otp/verify", methods=["POST"])
@limiter.limit("10 per 10 minutes", methods=["POST"])
def verify_login_otp():

    role = request.form.get("role", "").strip().lower()
    otp = request.form.get("otp", "").strip()

    login_pages = {
        "student": "student_login",
        "owner": "owner_login",
        "food_owner": "food_owner_login"
    }

    dashboard_pages = {
        "student": "student_dashboard",
        "owner": "owner_dashboard",
        "food_owner": "food_owner_dashboard"
    }

    if role not in login_pages:
        flash("Invalid OTP request.")
        return redirect(url_for("otp_login"))

    challenge_id = session.get("login_otp_challenge_id")

    try:
        challenge = None

        if challenge_id:
            challenge = LoginOTP.query.filter_by(
                id=challenge_id,
                role=role,
                used=False
            ).first()

        if not challenge:
            flash("Please request a new OTP.")
            return redirect(url_for("otp_login"))

        # Check expiration
        if datetime.utcnow() >= challenge.expires_at:

            challenge.used = True
            db.session.commit()

            session.pop("login_otp_challenge_id", None)

            flash("OTP expired. Please request a new one.")
            return redirect(url_for("otp_login"))

        # Maximum five verification attempts
        if challenge.attempts >= 5:

            challenge.used = True
            db.session.commit()

            session.pop("login_otp_challenge_id", None)

            flash("Too many incorrect attempts. Request a new OTP.")
            return redirect(url_for("otp_login"))

        # Validate six-digit format
        if len(otp) != 6 or not otp.isdigit():

            challenge.attempts += 1

            if challenge.attempts >= 5:
                challenge.used = True

            db.session.commit()

            if challenge.attempts >= 5:
                session.pop("login_otp_challenge_id", None)
                flash("Too many incorrect attempts. Request a new OTP.")
            else:
                flash("Invalid OTP.")

            return redirect(url_for("otp_login"))

        # Compare supplied OTP hash
        supplied_hash = hashlib.sha256(
            otp.encode("utf-8")
        ).hexdigest()

        if not hmac.compare_digest(
            supplied_hash,
            challenge.otp_hash
        ):

            challenge.attempts += 1

            if challenge.attempts >= 5:
                challenge.used = True

            db.session.commit()

            if challenge.attempts >= 5:
                session.pop("login_otp_challenge_id", None)
                flash("Too many incorrect attempts. Request a new OTP.")
            else:
                flash("Invalid OTP. Please try again.")

            return redirect(url_for("otp_login"))

        # OTP is correct
        user = db.session.get(User, challenge.user_id)

        if not user or user.role != role:

            challenge.used = True
            db.session.commit()

            session.pop("login_otp_challenge_id", None)

            flash("Unable to verify login. Please try again.")
            return redirect(url_for("otp_login"))

        # Mark OTP as used before creating authenticated session
        challenge.used = True
        db.session.commit()

        # Clear previous session data
        session.clear()

        # Create authenticated session
        session["user_id"] = user.id
        session["role"] = user.role
        session["name"] = user.name

        return redirect(url_for(dashboard_pages[role]))

    except SQLAlchemyError:

        db.session.rollback()

        app.logger.exception(
            "Database error during OTP verification."
        )

        session.pop("login_otp_challenge_id", None)

        flash(
            "A database error occurred during verification. "
            "Please request a new OTP.",
            "danger"
        )

        return redirect(url_for("otp_login"))
################### Admin login##############

@app.route("/admin-login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def admin_login():

    if request.method == "POST":

        email = request.form["email"].strip()
        password = request.form["password"]

        admin = User.query.filter_by(
            email=email,
            role="admin"
        ).first()

        if admin and check_password_hash(
            admin.password,
            password
        ):

            session.clear()

            session["user_id"] = admin.id
            session["role"] = "admin"
            session["name"] = admin.name

            return redirect(
                url_for("admin_dashboard")
            )

        flash("Invalid admin email or password.")

    return render_template("admin_login.html")

    ###################admin dashboard#########################

@app.route("/admin-dashboard")
def admin_dashboard():

    # =========================
    # ADMIN AUTHENTICATION
    # =========================

    if (
        "user_id" not in session
        or session.get("role") != "admin"
    ):
        flash("Access denied. Admin only.")
        return redirect(url_for("admin_login"))

    # =========================
    # DEFAULT VALUES
    # =========================

    total_users = 0
    total_students = 0
    total_owners = 0
    total_pgs = 0
    total_reviews = 0
    total_reports = 0
    pending_reports = 0

    users = []
    pgs = []
    reports = []
    reviews = []

    # =========================
    # DATABASE OPERATIONS
    # =========================

    try:

        # STATISTICS

        total_users = User.query.count()

        total_students = User.query.filter_by(
            role="student"
        ).count()

        total_owners = User.query.filter_by(
            role="owner"
        ).count()

        total_pgs = PG.query.count()

        total_reviews = Review.query.count()

        total_reports = Report.query.count()

        pending_reports = Report.query.filter_by(
            status="pending"
        ).count()

        # USERS

        users = User.query.order_by(
            User.id.desc()
        ).all()

        # PGs

        pgs = PG.query.order_by(
            PG.id.desc()
        ).all()

        # REPORTS

        reports = Report.query.order_by(
            Report.created_at.desc()
        ).all()

        # REVIEWS

        review_records = db.session.query(
            Review,
            User.name,
            PG.name
        ).outerjoin(
            User,
            Review.student_id == User.id
        ).outerjoin(
            PG,
            Review.pg_id == PG.id
        ).order_by(
            Review.created_at.desc()
        ).all()

        for review, student_name, pg_name in review_records:

            reviews.append({

                "id": review.id,

                "rating": review.rating,

                "comment": review.comment,

                "created_at": review.created_at,

                "student_name": (
                    student_name or "Unknown Student"
                ),

                "pg_name": (
                    pg_name or "Deleted PG"
                )

            })

    except SQLAlchemyError:

        db.session.rollback()

        app.logger.exception(
            "Database error while loading admin dashboard."
        )

        flash(
            "Unable to load dashboard data. Please try again.",
            "danger"
        )

    # =========================
    # RENDER DASHBOARD
    # =========================

    return render_template(
        "admin_dashboard.html",

        total_users=total_users,
        total_students=total_students,
        total_owners=total_owners,

        total_pgs=total_pgs,
        total_reviews=total_reviews,

        total_reports=total_reports,
        pending_reports=pending_reports,

        users=users,
        pgs=pgs,
        reviews=reviews,
        reports=reports
    )

# =========================
# FOOD OWNER: REQUEST SUBSCRIPTION PAYMENT
# =========================

@app.route("/food-business/<int:business_id>/renew", methods=["GET", "POST"])
@role_required("food_owner")
def food_business_renewal(business_id):
    business = FoodBusiness.query.filter_by(
        id=business_id, owner_id=session["user_id"]
    ).first_or_404()

    plan_key = request.values.get("plan", "").strip().lower()
    plan = FOOD_SUBSCRIPTION_PLANS.get(plan_key)
    payment_uri = None
    qr_image = None

    if plan:
        # UPI QR payload uses the exact fixed amount for the selected plan.
        params = {
            "pa": FOOD_SUBSCRIPTION_UPI_ID,
            "pn": "Food Finder Subscription",
            "am": str(plan["amount"]),
            "cu": "INR",
            "tn": f"Food subscription {business.id} {plan_key}",
        }
        payment_uri = "upi://pay?" + urlencode(params)
        try:
            import qrcode
            qr = qrcode.make(payment_uri)
            buffer = BytesIO()
            qr.save(buffer, format="PNG")
            qr_image = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        except ImportError:
            flash("QR code support is not installed. Run: pip install qrcode[pil]")

    if request.method == "POST":
        if not plan:
            flash("Please select a valid subscription plan.")
            return redirect(url_for("food_business_renewal", business_id=business.id))

        utr = request.form.get("transaction_reference", "").strip()
        if not re.fullmatch(r"[A-Za-z0-9-]{6,100}", utr):
            flash("Enter a valid transaction reference/UTR (6–100 letters, digits or hyphens).")
            return render_template("food_subscription_payment.html", business=business,
                                   plans=FOOD_SUBSCRIPTION_PLANS, selected_plan=plan_key,
                                   plan=plan, payment_uri=payment_uri, qr_image=qr_image)

        if FoodSubscriptionPaymentRequest.query.filter_by(transaction_reference=utr).first():
            flash("This transaction reference has already been submitted.")
            return render_template("food_subscription_payment.html", business=business,
                                   plans=FOOD_SUBSCRIPTION_PLANS, selected_plan=plan_key,
                                   plan=plan, payment_uri=payment_uri, qr_image=qr_image)

        proof = request.files.get("payment_screenshot")
        proof_path = None

        if proof and proof.filename:
            safe_name = secure_filename(proof.filename)

            if not allowed_image(safe_name):
                flash("Optional payment screenshot must be JPG, PNG or WebP.")
                return render_template(
                    "food_subscription_payment.html",
                    business=business,
                    plans=FOOD_SUBSCRIPTION_PLANS,
                    selected_plan=plan_key,
                    plan=plan,
                    payment_uri=payment_uri,
                    qr_image=qr_image
                )

            proof.stream.seek(0)
            image_bytes = proof.stream.read(MAX_MENU_PHOTO_SIZE + 1)
            proof.stream.seek(0)

            if len(image_bytes) > MAX_MENU_PHOTO_SIZE or not validate_image(proof):
                flash("Screenshot must be a valid image no larger than 5 MB.")
                return render_template(
                    "food_subscription_payment.html",
                    business=business,
                    plans=FOOD_SUBSCRIPTION_PLANS,
                    selected_plan=plan_key,
                    plan=plan,
                    payment_uri=payment_uri,
                    qr_image=qr_image
                )

            extension = safe_name.rsplit(".", 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{extension}"

            # Store payment proof privately in DBByte
            object_name = f"payment-proofs/{filename}"

            proof_path = upload_file(proof, object_name)

            if not proof_path:
                flash("Could not upload payment screenshot. Please try again.")
                return redirect(
                    url_for(
                        "food_business_renewal",
                        business_id=business.id,
                        plan=plan_key
                    )
                )
        payment_request = FoodSubscriptionPaymentRequest(
            business_id=business.id,
            owner_id=session["user_id"],
            plan=plan_key,
            amount=plan["amount"],
            transaction_reference=utr,
            proof_image=proof_path,
            status="pending",
        )
        try:
            db.session.add(payment_request)
            db.session.commit()
        except Exception:
            db.session.rollback()

            # Delete uploaded screenshot if database saving fails
            if proof_path:
                delete_file(proof_path)

            app.logger.exception(
                "Could not save food subscription payment request"
            )

            flash("Could not submit payment request. Please try again.")

            return redirect(
                url_for(
                    "food_business_renewal",
                    business_id=business.id,
                    plan=plan_key
                )
            )
        flash("Payment request submitted. Your subscription will change only after admin verifies the payment.")
        return redirect(url_for("food_owner_dashboard"))

    requests_for_business = FoodSubscriptionPaymentRequest.query.filter_by(
        business_id=business.id
    ).order_by(FoodSubscriptionPaymentRequest.created_at.desc()).all()
    return render_template(
        "food_subscription_payment.html", business=business,
        plans=FOOD_SUBSCRIPTION_PLANS, selected_plan=plan_key,
        plan=plan, payment_uri=payment_uri, qr_image=qr_image,
        payment_requests=requests_for_business
    )


# =========================
# ADMIN: VIEW PAYMENT PROOF
# =========================

@app.route("/admin/payment-proof/<int:payment_id>")
def view_payment_proof(payment_id):

    # Only admins can view payment screenshots
    if "user_id" not in session or session.get("role") != "admin":
        abort(403)

    payment = db.session.get(
        FoodSubscriptionPaymentRequest,
        payment_id
    )

    if payment is None or not payment.proof_image:
        abort(404)

    # New DBByte payment screenshots
    if payment.proof_image.startswith("payment-proofs/"):

        image_data = download_file(payment.proof_image)

        if not image_data:
            abort(404)

        content_type = mimetypes.guess_type(
            payment.proof_image
        )[0]

        return send_file(
            BytesIO(image_data),
            mimetype=content_type or "application/octet-stream",
            as_attachment=False
        )

    # Support older locally stored screenshots
    return send_from_directory(
        PAYMENT_PROOF_FOLDER,
        payment.proof_image,
        as_attachment=False
    )

@app.route("/admin/food-payment/<int:payment_id>/review", methods=["POST"])
def review_food_subscription_payment(payment_id):
    if "user_id" not in session or session.get("role") != "admin":
        flash("Access denied. Admin only.")
        return redirect(url_for("admin_login"))

    try:
        payment = db.session.get(
            FoodSubscriptionPaymentRequest,
            payment_id
        )
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception(
            "Database error while fetching payment request ID %s",
            payment_id
        )
        flash("Unable to load payment request. Please try again.", "danger")
        return redirect(url_for("admin_food_businesses"))
    if payment is None:
        flash("Payment request not found.")
        return redirect(url_for("admin_food_businesses"))
    if payment.status != "pending":
        flash("This payment request has already been reviewed. It cannot be processed twice.")
        return redirect(url_for("admin_food_businesses"))

    action = request.form.get("action", "").strip().lower()
    note = request.form.get("admin_note", "").strip()[:500]
    
    if action == "reject":
        try:
            payment.status = "rejected"
            payment.admin_note = note or "Payment not approved by admin."
            payment.reviewed_at = datetime.utcnow()

            # Notify the food business owner
            db.session.add(Notification(
                user_id=payment.owner_id,
                title="Subscription payment rejected",
                message=(
                    f"Your {payment.plan.title()} subscription payment request for "
                    f"{payment.business.business_name} was rejected. "
                    f"Admin note: {payment.admin_note}"
                ),
                notification_type="subscription_payment"
            ))

            db.session.commit()

        except SQLAlchemyError:
            db.session.rollback()

            app.logger.exception(
                "Failed to reject food subscription payment."
            )

            flash("Payment rejection failed. No changes were saved.")
            return redirect(url_for("admin_food_businesses"))

        flash("Payment request rejected. Existing subscription was not changed.")
        return redirect(url_for("admin_food_businesses"))

    if action != "approve":
        flash("Invalid payment review action.")
        return redirect(url_for("admin_food_businesses"))

    try:
        business = db.session.get(FoodBusiness, payment.business_id)
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception(
            "Database error while fetching food business for payment ID %s",
            payment_id
        )
        flash("Unable to load food business details. Please try again.", "danger")
        return redirect(url_for("admin_food_businesses"))
    plan = FOOD_SUBSCRIPTION_PLANS.get(payment.plan)
    if business is None or plan is None or payment.amount != plan["amount"]:
        flash("Payment request details are invalid; no subscription change was made.")
        return redirect(url_for("admin_food_businesses"))

    now = datetime.utcnow()
    if (business.subscription_status == "active"
            and business.subscription_expiry_date is not None
            and business.subscription_expiry_date > now):
        start_date = business.subscription_expiry_date
    else:
        start_date = now

    expiry_date = start_date + timedelta(days=plan["days"])
    business.subscription_plan = payment.plan
    business.subscription_start_date = now
    business.subscription_expiry_date = expiry_date
    business.subscription_status = "active"
    payment.status = "approved"
    payment.admin_note = note or "Payment verified in UPI account."
    payment.reviewed_at = now

    # Notify the food business owner that the subscription was activated/extended.
    db.session.add(Notification(
        user_id=payment.owner_id,
        title="Subscription payment approved",
        message=(
            f"Your {payment.plan.title()} subscription payment for "
            f"{business.business_name} was approved. Your subscription is active "
            f"until {expiry_date.strftime('%d-%m-%Y')}."
        ),
        notification_type="subscription_payment"
    ))

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Failed to approve food subscription payment")
        flash("Approval failed. No changes were saved.")
        return redirect(url_for("admin_food_businesses"))

    flash(f"Verified payment approved. {business.business_name} subscription now expires on {expiry_date.strftime('%d-%m-%Y')}.")
    return redirect(url_for("admin_food_businesses"))


# =========================
# ADMIN: MANAGE FOOD BUSINESSES
# =========================

@app.route("/admin/food-businesses")
def admin_food_businesses():

    if (
        "user_id" not in session
        or session.get("role") != "admin"
    ):
        flash("Access denied. Admin only.")
        return redirect(url_for("admin_login"))

    update_expired_subscriptions()

    businesses = FoodBusiness.query.order_by(
        FoodBusiness.created_at.desc()
    ).all()

    # Prepare menu photos for display
    for business in businesses:
        try:
            photo_paths = json.loads(
                business.menu_photos or "[]"
            )

            if not isinstance(photo_paths, list):
                photo_paths = []

            business.display_menu_photos = [
                path for path in photo_paths
                if (
                    isinstance(path, str)
                    and path.startswith("uploads/food_menus/")
                    and ".." not in path.split("/")
                )
            ]

        except (json.JSONDecodeError, TypeError):
            business.display_menu_photos = []

    payment_requests = FoodSubscriptionPaymentRequest.query.order_by(
        FoodSubscriptionPaymentRequest.created_at.desc()
    ).all()

    return render_template(
        "admin_food_businesses.html",
        businesses=businesses,
        payment_requests=payment_requests
    )
# =========================
# ADMIN: VERIFY FOOD BUSINESS
# =========================

@app.route(
    "/admin/food-business/<int:business_id>/verification",
    methods=["POST"]
)
def update_food_business_verification(business_id):

    if (
        "user_id" not in session
        or session.get("role") != "admin"
    ):
        flash("Access denied. Admin only.")
        return redirect(url_for("admin_login"))

    try:
        business = db.session.get(
            FoodBusiness,
            business_id
        )

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching food business ID %s",
            business_id
        )

        flash(
            "Unable to load food business details. Please try again.",
            "danger"
        )

        return redirect(url_for("admin_food_businesses"))
    if business is None:
        flash("Food business not found.")
        return redirect(url_for("admin_food_businesses"))

    action = request.form.get(
        "action", ""
    ).strip().lower()

    if action == "approve":
        business.verification_status = "verified"

    elif action == "reject":
        business.verification_status = "rejected"

    else:
        flash("Invalid verification action.")
        return redirect(url_for("admin_food_businesses"))

    try:
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Failed to update food business verification status."
        )

        flash(
            "Unable to update verification status. Please try again.",
            "danger"
        )

        return redirect(url_for("admin_food_businesses"))

    if action == "approve":
        flash("Food business verified successfully.")
    else:
        flash("Food business rejected.")

    return redirect(url_for("admin_food_businesses"))

# =========================
# ADMIN: MANAGE SUBSCRIPTION
# =========================

@app.route(
    "/admin/food-business/<int:business_id>/subscription",
    methods=["POST"]
)
def update_food_business_subscription(business_id):

    # Admin authentication
    if (
        "user_id" not in session
        or session.get("role") != "admin"
    ):
        flash("Access denied. Admin only.")
        return redirect(url_for("admin_login"))

    # Find the business
    try:
        business = db.session.get(
            FoodBusiness,
            business_id
        )

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching food business ID %s",
            business_id
        )

        flash(
            "Unable to load food business details. Please try again.",
            "danger"
        )

        return redirect(url_for("admin_food_businesses"))

    if business is None:
        flash("Food business not found.")
        return redirect(url_for("admin_food_businesses"))

    action = request.form.get(
        "action", ""
    ).strip().lower()

    # Direct activation is disabled
    if action == "activate":
        flash(
            "Direct activation is disabled. Verify and approve "
            "a payment request instead."
        )
        return redirect(url_for("admin_food_businesses"))

    # Deactivate subscription
    elif action == "deactivate":

        business.subscription_status = "inactive"

        try:
            db.session.commit()

        except SQLAlchemyError:
            db.session.rollback()

            app.logger.exception(
                "Failed to deactivate food business subscription."
            )

            flash(
                "Unable to deactivate subscription. Please try again.",
                "danger"
            )

            return redirect(url_for("admin_food_businesses"))

        flash(
            f"Subscription deactivated for "
            f"{business.business_name}."
        )

    else:
        flash("Invalid subscription action.")

    # This return must remain outside the if-elif-else blocks
    return redirect(url_for("admin_food_businesses"))        

##########admin:delete pg#############################
    
@app.route(
    "/admin/delete-pg/<int:pg_id>",
    methods=["POST"]
)
def admin_delete_pg(pg_id):

    if (
        "user_id" not in session
        or session.get("role") != "admin"
    ):
        return redirect(url_for("admin_login"))

    try:
        pg = PG.query.get_or_404(pg_id)

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching PG ID %s for admin deletion",
            pg_id
        )

        flash("Unable to load PG listing. Please try again.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        Report.query.filter_by(
            pg_id=pg.id
        ).delete(synchronize_session=False)

        # Delete reviews associated with PG
        Review.query.filter_by(
            pg_id=pg.id
        ).delete(synchronize_session=False)

        # Delete saved PG records
        SavedPG.query.filter_by(
            pg_id=pg.id
        ).delete(synchronize_session=False)

        # Delete PG
        db.session.delete(pg)

        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Failed to delete PG listing from admin dashboard."
        )

        flash(
            "Unable to delete PG listing. Please try again.",
            "danger"
        )

        return redirect(url_for("admin_dashboard"))

    flash("PG listing deleted successfully.")

    return redirect(url_for("admin_dashboard"))

#############admin:delete review#######################
     
@app.route(
    "/admin/delete-review/<int:review_id>",
    methods=["POST"]
)
def admin_delete_review(review_id):

    if (
        "user_id" not in session
        or session.get("role") != "admin"
    ):
        return redirect(url_for("admin_login"))

    try:
        review = Review.query.get_or_404(review_id)

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching review ID %s",
            review_id
        )

        flash("Unable to load review. Please try again.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        db.session.delete(review)
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Failed to delete review from admin dashboard."
        )

        flash(
            "Unable to delete review. Please try again.",
            "danger"
        )

        return redirect(url_for("admin_dashboard"))

    flash("Review deleted successfully.")

    return redirect(url_for("admin_dashboard"))
# =========================================
# VERIFY OWNER
# =========================================

@app.route(
    "/admin/verify-owner/<int:user_id>/<action>",
    methods=["POST"]
)
def verify_owner(user_id, action):

    # Only administrators can verify owners
    if (
        "user_id" not in session
        or session.get("role") != "admin"
    ):
        flash("You are not authorized to perform this action.")
        return redirect(url_for("admin_login"))

    # Validate action
    if action not in {"verify", "reject"}:
        flash("Invalid verification action.")
        return redirect(url_for("admin_dashboard"))

    # Find user
    try:
        user = db.session.get(User, user_id)

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching owner ID %s",
            user_id
        )

        flash("Unable to load owner details. Please try again.")
        return redirect(url_for("admin_dashboard"))

    if user is None:
        flash("User not found.")
        return redirect(url_for("admin_dashboard"))

    # Ensure the user is an owner
    if user.role != "owner":
        flash("This user is not an owner.")
        return redirect(url_for("admin_dashboard"))

    # Update verification status
    if action == "verify":
        user.verification_status = "verified"
        success_message = f"Owner {user.name} has been verified."

    else:
        user.verification_status = "rejected"
        success_message = f"Owner {user.name} has been rejected."

    # Save changes
    try:
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Failed to update verification for owner ID %s",
            user_id
        )

        flash("Unable to update owner verification. Please try again.")
        return redirect(url_for("admin_dashboard"))

    flash(success_message)

    return redirect(url_for("admin_dashboard"))

# =========================================
# VERIFY PG
# =========================================

@app.route(
    "/admin/verify-pg/<int:pg_id>/<action>",
    methods=["POST"]
)
def verify_pg(pg_id, action):

    # 1. Only administrators can verify PGs
    if (
        "user_id" not in session
        or session.get("role") != "admin"
    ):
        flash("You are not authorized to perform this action.")
        return redirect(url_for("admin_login"))

    # 2. Validate action
    if action not in {"verify", "reject"}:
        flash("Invalid verification action.")
        return redirect(url_for("admin_dashboard"))

    # 3. Find PG
    try:
        pg = db.session.get(PG, pg_id)

    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception(
            "Database error while fetching PG ID %s",
            pg_id
        )
        flash("Unable to load PG details. Please try again.")
        return redirect(url_for("admin_dashboard"))

    if pg is None:
        flash("PG not found.")
        return redirect(url_for("admin_dashboard"))

    # 4. Find owner
    try:
        owner = db.session.get(User, pg.owner_id)

    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception(
            "Database error while fetching owner of PG ID %s",
            pg_id
        )
        flash("Unable to load owner details. Please try again.")
        return redirect(url_for("admin_dashboard"))

    if owner is None or owner.role != "owner":
        flash("PG owner could not be found or is invalid.")
        return redirect(url_for("admin_dashboard"))

    # 5. Update status and create notification
    try:

        if action == "verify":

            pg.verification_status = "verified"

            notification_title = "PG Verified"

            notification_message = (
                f'Your PG "{pg.name}" has been verified '
                "and is now visible to students."
            )

            success_message = f"PG {pg.name} has been verified."

        else:

            pg.verification_status = "rejected"

            notification_title = "PG Verification Update"

            notification_message = (
                f'Your PG "{pg.name}" has been rejected. '
                "Please review the listing information."
            )

            success_message = f"PG {pg.name} has been rejected."

        notification = Notification(
            user_id=owner.id,
            title=notification_title,
            message=notification_message,
            notification_type="pg_verification",
            is_read=False
        )

        db.session.add(notification)

        # Save PG status and notification together
        db.session.commit()

    except SQLAlchemyError:

        db.session.rollback()

        app.logger.exception(
            "Failed to update verification for PG ID %s",
            pg_id
        )

        flash("Unable to update PG verification. Please try again.")
        return redirect(url_for("admin_dashboard"))

    # 6. Display success message
    flash(success_message)

    return redirect(url_for("admin_dashboard"))

#=========================================
# ADMIN REPORT ACTION
# =========================================

@app.route(
    "/admin/report/<int:report_id>/<action>",
    methods=["POST"]
)
def admin_report_action(report_id, action):

    # 1. Only administrators can manage reports
    if (
        "user_id" not in session
        or session.get("role") != "admin"
    ):
        flash("Please log in as an administrator.")
        return redirect(url_for("admin_login"))

    # 2. Validate the requested action
    allowed_actions = {
        "resolve": "resolved",
        "dismiss": "dismissed",
        "pending": "pending"
    }

    if action not in allowed_actions:
        flash("Invalid report action.")
        return redirect(url_for("admin_dashboard"))

    # 3. Find the report
    try:
        report = db.session.get(Report, report_id)

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching report ID %s",
            report_id
        )

        flash("Unable to load the report. Please try again.")
        return redirect(url_for("admin_dashboard"))

    if report is None:
        flash("Report not found.")
        return redirect(url_for("admin_dashboard"))

    # 4. Validate the admin note
    admin_note = request.form.get(
        "admin_note",
        ""
    ).strip()

    if len(admin_note) > 1000:
        flash("Admin note cannot exceed 1000 characters.")
        return redirect(url_for("admin_dashboard"))

    # 5. Update report status and note
    report.status = allowed_actions[action]
    report.admin_note = admin_note

    # 6. Save changes safely
    try:
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Databse error while updating report ID %s",
            report_id
        )

        flash("Unable to update the report. Please try again.")
        return redirect(url_for("admin_dashboard"))

    # 7. Display the appropriate success message
    messages = {
        "resolve": "Report marked as resolved.",
        "dismiss": "Report dismissed.",
        "pending": "Report moved back to pending."
    }

    flash(messages[action])

    return redirect(url_for("admin_dashboard"))
# =========================================
# NOTIFICATIONS
# =========================================

@app.route("/notifications")
def notifications():

    if "user_id" not in session:
        return redirect(url_for("login"))

    notification_list = Notification.query.filter_by(
        user_id=session["user_id"]
    ).order_by(
        Notification.created_at.desc()
    ).all()

    unread_count = Notification.query.filter_by(
        user_id=session["user_id"],
        is_read=False
    ).count()

    return render_template(
        "notifications.html",
        notifications=notification_list,
        unread_count=unread_count
    )

# =========================================
# MARK NOTIFICATION AS READ
# =========================================

@app.route(
    "/notification/read/<int:notification_id>",
    methods=["POST"]
)
def mark_notification_read(notification_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        notification = Notification.query.get_or_404(
            notification_id
        )

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching notification ID %s",
            notification_id
        )

        flash("Unable to load notification. Please try again.", "danger")
        return redirect(url_for("notifications"))
    if notification.user_id != session["user_id"]:
        flash("You are not authorized to access this notification.")
        return redirect(url_for("notifications"))

    notification.is_read = True

    try:
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while marking notification ID %s as read.",
            notification_id
        )

        flash(
            "Unable to update notification. Please try again.",
            "danger"
        )

    return redirect(url_for("notifications"))
# =========================
# STUDENT DASHBOARD
# =========================

@app.route("/student")
@role_required("student")
def student_dashboard():

    if "user_id" not in session or session.get("role") != "student":
        flash("Access denied.Students only")
        return redirect(url_for("student_login"))

    return render_template(
        "student_dashboard.html",
        name=session.get("name")
    )

# =========================
# NEARBY PGs
# =========================
@app.route("/nearby-pgs")
def nearby_pgs():

    from math import isfinite

    # =========================
    # STUDENT AUTHENTICATION
    # =========================

    if (
        "user_id" not in session
        or session.get("role") != "student"
    ):
        return redirect(url_for("student_login"))

    # =========================
    # GET USER LOCATION
    # =========================

    latitude = request.args.get("latitude", type=float)
    longitude = request.args.get("longitude", type=float)

    nearby_list = []

    # Validate coordinates

    if (
        latitude is not None
        and longitude is not None
        and (
            not isfinite(latitude)
            or not isfinite(longitude)
            or not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        )
    ):
        latitude = None
        longitude = None

    # =========================
    # FETCH VERIFIED PGs
    # =========================

    if latitude is not None and longitude is not None:

        try:

            pgs = PG.query.join(
                User,
                PG.owner_id == User.id
            ).filter(
                PG.verification_status == "verified",
                User.verification_status == "verified",
                User.role == "owner",
                PG.latitude.isnot(None),
                PG.longitude.isnot(None)
            ).all()

            # =========================
            # CALCULATE DISTANCE
            # =========================

            for pg in pgs:

                R = 6371.0

                lat1 = radians(latitude)
                lon1 = radians(longitude)

                lat2 = radians(pg.latitude)
                lon2 = radians(pg.longitude)

                dlat = lat2 - lat1
                dlon = lon2 - lon1

                a = (
                    sin(dlat / 2) ** 2
                    + cos(lat1)
                    * cos(lat2)
                    * sin(dlon / 2) ** 2
                )

                a = max(0.0, min(1.0, a))

                c = 2 * atan2(
                    sqrt(a),
                    sqrt(1 - a)
                )

                distance = R * c

                nearby_list.append({
                    "pg": pg,
                    "distance": round(distance, 2)
                })

            # Sort nearest PG first

            nearby_list.sort(
                key=lambda x: x["distance"]
            )

        except SQLAlchemyError:

            db.session.rollback()

            app.logger.exception(
                "Database error while loading nearby PGs."
            )

            flash(
                "Unable to load nearby PGs right now. Please try again.",
                "danger"
            )

    # =========================
    # RENDER TEMPLATE
    # =========================

    return render_template(
        "nearby_pgs.html",
        name=session.get("name"),
        nearby_pgs=nearby_list,
        latitude=latitude,
        longitude=longitude
    )

# =========================
# VALIDATE COORDINATES
# =========================

def validate_coordinates(latitude, longitude):
    """Validate latitude and longitude values."""

    try:
        lat = float(latitude)
        lon = float(longitude)

    except (ValueError, TypeError):
        return False

    if not math.isfinite(lat) or not math.isfinite(lon):
        return False

    return (
        -90 <= lat <= 90
        and -180 <= lon <= 180
    )


# =========================
# ADD PG
# =========================


@app.route("/add-pg", methods=["GET", "POST"])
def add_pg():

    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("owner_login"))

    if request.method == "POST":

        validation_error = validate_pg_form(request.form)

        if validation_error:
            flash(validation_error)
            return render_template("add_pg.html")

        name = request.form["name"].strip()
        address = request.form["address"].strip()
        gender = request.form["gender"]

        total_rooms = request.form["total_rooms"]
        available_rooms = request.form["available_rooms"]

        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        if not validate_coordinates(latitude, longitude):
            flash("Please enter valid latitude and longitude values.")
            return render_template("add_pg.html")

        wifi = "wifi" in request.form
        laundry = "laundry" in request.form
        ac = "ac" in request.form
        cctv = "cctv" in request.form
        power_backup = "power_backup" in request.form

        description = request.form["description"].strip()
        contact = request.form["contact"].strip()

        # =========================
        # FRONT IMAGE
        # =========================

        front_image = request.files.get("front_image")
        front_image_filename = None

        if front_image and front_image.filename:

            if not allowed_image(front_image.filename):
                flash("Invalid image format. Please upload JPG, JPEG, PNG or WEBP.")
                return render_template("add_pg.html")

            front_image.seek(0, os.SEEK_END)
            image_size = front_image.tell()
            front_image.seek(0)

            if image_size > MAX_PG_IMAGE_SIZE:
                flash("Image must be 5 MB or smaller.")
                return render_template("add_pg.html")

            if not validate_image(front_image):
                flash("The uploaded file is not a valid image.")
                return render_template("add_pg.html")

            original_filename = secure_filename(front_image.filename)

            if not original_filename:
                flash("Invalid filename. Please rename the image and try again.")
                return render_template("add_pg.html")

            unique_filename = str(uuid.uuid4()) + "_" + original_filename

            # Upload directly to DBByte
            object_name = "pg-images/" + unique_filename

            front_image_filename = upload_file(
                front_image,
                object_name
            )

            if not front_image_filename:
                flash("Unable to upload PG image. Please try again.")
                return render_template("add_pg.html")

        # =========================
        # CREATE PG
        # =========================

        new_pg = PG(
            owner_id=session["user_id"],
            name=name,
            address=address,
            latitude=float(latitude),
            longitude=float(longitude),
            gender=gender,
            total_rooms=int(total_rooms),
            available_rooms=int(available_rooms),
            wifi=wifi,
            laundry=laundry,
            ac=ac,
            cctv=cctv,
            power_backup=power_backup,
            description=description,
            contact=contact,
            front_image=front_image_filename
        )

        try:
            db.session.add(new_pg)
            db.session.commit()

        except SQLAlchemyError:
            db.session.rollback()

            # Delete uploaded DBByte image if database insertion fails
            if front_image_filename:
                delete_file(front_image_filename)

            app.logger.exception("Failed to create PG")

            flash("Unable to add the PG right now. Please try again.")
            return render_template("add_pg.html")

        flash("PG added successfully with location!")

        return redirect(url_for("owner_dashboard"))

    return render_template("add_pg.html")

# =========================
# EDIT PG
# =========================

@app.route("/edit-pg/<int:pg_id>", methods=["GET", "POST"])
def edit_pg(pg_id):

    # Only owners can edit PGs
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("owner_login"))

    pg = PG.query.get_or_404(pg_id)

    # Make sure this PG belongs to the logged-in owner
    if pg.owner_id != session["user_id"]:
        flash("You are not authorized to edit this PG.")
        return redirect(url_for("owner_dashboard"))

    if request.method == "POST":

        # =========================
        # VALIDATE PG DETAILS
        # =========================

        validation_error = validate_pg_form(request.form)

        if validation_error:
            flash(validation_error)
            return render_template("edit_pg.html", pg=pg)

        # =========================
        # RECEIVE AND VALIDATE IMAGE
        # =========================

        front_image = request.files.get("front_image")
        new_image_filename = None
        uploaded_object_name = None
        old_image_filename = pg.front_image

        if front_image and front_image.filename:

            if not allowed_image(front_image.filename):
                flash(
                    "Invalid image format. "
                    "Please upload JPG, JPEG, PNG or WEBP."
                )
                return render_template("edit_pg.html", pg=pg)

            # Check individual image size (maximum 5 MB)
            front_image.seek(0, os.SEEK_END)
            image_size = front_image.tell()
            front_image.seek(0)

            if image_size > MAX_PG_IMAGE_SIZE:
                flash(
                    "Image is too large! Please upload smaller than 5 MB.",
                    "error"
                )
                return render_template("edit_pg.html", pg=pg)

            if not validate_image(front_image):
                flash(
                    "The uploaded file is not a valid image. "
                    "Please upload a valid JPG, PNG or WEBP image."
                )
                return render_template("edit_pg.html", pg=pg)

            original_filename = secure_filename(front_image.filename)

            if not original_filename:
                flash(
                    "Invalid filename. Please rename the image and try again."
                )
                return render_template("edit_pg.html", pg=pg)

            new_image_filename = (
                str(uuid.uuid4()) + "_" + original_filename
            )

        # =========================
        # UPDATE PG DETAILS
        # =========================

        try:
            pg.name = request.form["name"].strip()
            pg.address = request.form["address"].strip()
            pg.gender = request.form["gender"]

            pg.total_rooms = int(request.form["total_rooms"])
            pg.available_rooms = int(request.form["available_rooms"])

            pg.wifi = "wifi" in request.form
            pg.laundry = "laundry" in request.form
            pg.ac = "ac" in request.form
            pg.cctv = "cctv" in request.form
            pg.power_backup = "power_backup" in request.form

            pg.description = request.form["description"].strip()
            pg.contact = request.form["contact"].strip()

            # =========================
            # UPLOAD NEW IMAGE TO DBBYTE
            # =========================

            if new_image_filename:

                uploaded_object_name = (
                    "pg-images/" + new_image_filename
                )

                result = upload_file(
                    front_image,
                    uploaded_object_name
                )

                if not result:
                    raise RuntimeError(
                        "Unable to upload the new PG image to DBByte."
                    )

                # Store DBByte object name in database
                pg.front_image = result

            # Commit all PG changes together
            db.session.commit()

        except Exception:
            db.session.rollback()

            # Delete newly uploaded image if database update fails
            if uploaded_object_name:
                try:
                    delete_file(uploaded_object_name)
                except Exception:
                    app.logger.exception(
                        "Could not delete failed DBByte upload for PG ID %s",
                        pg_id
                    )

            app.logger.exception(
                "Failed to update PG ID %s",
                pg_id
            )

            flash("Unable to update the PG. Please try again.")
            return render_template("edit_pg.html", pg=pg)

        # =========================
        # DELETE OLD IMAGE AFTER SUCCESSFUL COMMIT
        # =========================

        if new_image_filename and old_image_filename:

            try:
                # Old images stored in DBByte
                if old_image_filename.startswith("pg-images/"):
                    delete_file(old_image_filename)

                # Legacy images stored locally
                elif "/" not in old_image_filename and "\\" not in old_image_filename:

                    old_image_path = os.path.join(
                        app.config["UPLOAD_FOLDER"],
                        old_image_filename
                    )

                    if os.path.isfile(old_image_path):
                        os.remove(old_image_path)

            except Exception:
                app.logger.exception(
                    "Could not remove previous image for PG ID %s",
                    pg_id
                )

        flash("PG updated successfully!")

        return redirect(url_for("owner_dashboard"))

    return render_template("edit_pg.html", pg=pg)
# =========================
# DELETE PG
# =========================

@app.route("/delete-pg/<int:pg_id>", methods=["POST"])
def delete_pg(pg_id):

    # Only logged-in owners can delete PGs
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("owner_login"))

    # Find the PG
    try:
        pg = PG.query.get_or_404(pg_id)

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching PG ID %s for deletion",
            pg_id
        )

        flash("Unable to load PG details right now. Please try again.")
        return redirect(url_for("owner_dashboard"))

    # Verify ownership
    if pg.owner_id != session["user_id"]:
        flash("You are not authorized to delete this PG.")
        return redirect(url_for("owner_dashboard"))

    try:
        # Delete related records first
        SavedPG.query.filter_by(pg_id=pg.id).delete(
            synchronize_session=False
        )

        Review.query.filter_by(pg_id=pg.id).delete(
            synchronize_session=False
        )

        Report.query.filter_by(pg_id=pg.id).delete(
            synchronize_session=False
        )

        # Remember the image filename before deleting the PG
        image_filename = pg.front_image

        # Delete the PG itself
        db.session.delete(pg)

        # Save all database changes first
        db.session.commit()

        # Remove the uploaded image after successful database deletion
        # Remove the uploaded image after successful database deletion
        if image_filename:
            try:
                # Delete image from DBByte
                if image_filename.startswith("pg-images/"):
                    delete_file(image_filename)

                # Delete old local image (backward compatibility)
                elif "/" not in image_filename and "\\" not in image_filename:
                    image_path = os.path.join(
                        app.config["UPLOAD_FOLDER"],
                        image_filename
                    )

                    if os.path.isfile(image_path):
                        os.remove(image_path)

            except Exception:
                app.logger.exception(
                    "Could not remove image for deleted PG ID %s",
                    pg_id
                )

        flash("PG and its related records deleted successfully!")
    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while deleting PG ID %s",
            pg_id
        )

        flash("Unable to delete this PG right now. Please try again.")
    return redirect(url_for("owner_dashboard"))
# =========================
# OWNER DASHBOARD
# =========================

@app.route("/owner")
@role_required("owner")
def owner_dashboard():

    if "user_id" not in session or session.get("role") != "owner":
        flash("Access denied.Owners only.")
        return redirect(url_for("owner_login"))

    owner_pgs = PG.query.filter_by(
        owner_id=session["user_id"]
    ).all()

    return render_template(
        "owner_dashboard.html",
        name=session.get("name"),
        pgs=owner_pgs
    )



# =========================
# FOOD BUSINESS OWNER DASHBOARD
# =========================

@app.route("/food-owner")
@role_required("food_owner")
def food_owner_dashboard():

    # Get the current time FIRST
    now = datetime.utcnow()

    # Update expired subscriptions
    update_expired_subscriptions()

    # Get businesses belonging to the logged-in owner
    businesses = FoodBusiness.query.filter_by(
        owner_id=session["user_id"]
    ).order_by(
        FoodBusiness.created_at.desc()
    ).all()

    # Prepare photos and subscription information
    for business in businesses:

        # Prepare menu photos
        try:
            photo_paths = json.loads(
                business.menu_photos or "[]"
            )

            if not isinstance(photo_paths, list):
                photo_paths = []

            
            business.display_menu_photos = [
                path for path in photo_paths
                if (
                    isinstance(path, str)
                    and (
                        path.startswith("food-menus/")
                        or path.startswith("uploads/food_menus/")
                    )
                    and ".." not in path.split("/")
                    and "\\" not in path
                )
            ]

        except (json.JSONDecodeError, TypeError):
            business.display_menu_photos = []

        # Calculate subscription days remaining
        expiry = business.subscription_expiry_date

        if (
            business.subscription_status == "active"
            and expiry is not None
            and expiry > now
        ):
            remaining = expiry - now

            business.days_remaining = (
                remaining.days
                + (1 if remaining.seconds > 0 else 0)
            )
        else:
            business.days_remaining = 0

    unread_notification_count = Notification.query.filter_by(
        user_id=session["user_id"],
        is_read=False
    ).count()        

    # Render dashboard
    return render_template(
        "food_owner_dashboard.html",
        name=session.get("name"),
        businesses=businesses,
        now=now,
        unread_notification_count=unread_notification_count
    )
# ==========================================
# EDIT FOOD BUSINESS
# ==========================================

@app.route("/food-business/<int:business_id>/edit", methods=["GET", "POST"])
@role_required("food_owner")
def edit_food_business(business_id):

    from math import isfinite

    business = FoodBusiness.query.filter_by(
        id=business_id,
        owner_id=session["user_id"]
    ).first_or_404()

    # Load existing menu photos
    try:
        menu_photos = json.loads(business.menu_photos or "[]")

        if not isinstance(menu_photos, list):
            menu_photos = []

    except (ValueError, TypeError):
        menu_photos = []

    if request.method == "POST":

        business_name = request.form.get(
            "business_name", ""
        ).strip()

        category = request.form.get(
            "category", ""
        ).strip()

        phone = request.form.get(
            "phone", ""
        ).strip()

        address = request.form.get(
            "address", ""
        ).strip()

        description = request.form.get(
            "description", ""
        ).strip()

        opening_hours = request.form.get(
            "opening_hours", ""
        ).strip()

        latitude_text = request.form.get(
            "latitude", ""
        ).strip()

        longitude_text = request.form.get(
            "longitude", ""
        ).strip()

        # Validate required fields
        if not all([
            business_name,
            category,
            phone,
            address
        ]):
            flash(
                "Please fill in all required fields.",
                "error"
            )

            return redirect(
                url_for(
                    "edit_food_business",
                    business_id=business.id
                )
            )

        # Validate coordinates
        try:
            latitude = (
                float(latitude_text)
                if latitude_text else None
            )

            longitude = (
                float(longitude_text)
                if longitude_text else None
            )

            if latitude is not None:
                if not isfinite(latitude) or not -90 <= latitude <= 90:
                    raise ValueError

            if longitude is not None:
                if not isfinite(longitude) or not -180 <= longitude <= 180:
                    raise ValueError

            # Both coordinates must be supplied together
            if (latitude is None) != (longitude is None):
                raise ValueError

        except ValueError:
            flash(
                "Enter valid latitude and longitude values.",
                "error"
            )

            return redirect(
                url_for(
                    "edit_food_business",
                    business_id=business.id
                )
            )

        # Update business details
        business.business_name = business_name
        business.category = category
        business.phone = phone
        business.address = address
        business.latitude = latitude
        business.longitude = longitude
        business.description = description
        business.opening_hours = opening_hours

        # ----------------------------------
        # REMOVE SELECTED MENU PHOTOS
        # ----------------------------------

        original_menu_photos = list(menu_photos)

        remove_photos = request.form.getlist("remove_photos")

        removed_photo_paths = [
            photo for photo in original_menu_photos
            if photo in remove_photos
        ]

        menu_photos = [
            photo for photo in original_menu_photos
            if photo not in remove_photos
        ]

        # ----------------------------------
        # VALIDATE NEW MENU PHOTOS
        # ----------------------------------

        uploaded_photos = request.files.getlist("menu_photos")

        allowed_extensions = {
            "jpg", "jpeg", "png", "webp"
        }

        upload_folder = os.path.join(
            app.root_path,
            "static",
            "uploads",
            "food_menus"
        )

        os.makedirs(upload_folder, exist_ok=True)

        valid_uploads = []

        # Validate all uploaded photos before saving any files
        for photo in uploaded_photos:

            if not photo or not photo.filename:
                continue

            original_name = secure_filename(photo.filename)

            if (
                "." not in original_name
                or original_name.rsplit(".", 1)[1].lower()
                not in allowed_extensions
            ):
                flash(
                    "Menu photos must be JPG, JPEG, PNG, or WEBP.",
                    "error"
                )

                return redirect(
                    url_for(
                        "edit_food_business",
                        business_id=business.id
                    )
                )

            # Maximum five photos
            if len(menu_photos) + len(valid_uploads) >= 5:
                flash(
                    "A maximum of five menu photos is allowed.",
                    "error"
                )

                return redirect(
                    url_for(
                        "edit_food_business",
                        business_id=business.id
                    )
                )

            # Check individual photo size
            photo.stream.seek(0, os.SEEK_END)
            image_size = photo.stream.tell()
            photo.stream.seek(0)

            if image_size == 0:
                flash(
                    "Empty menu photos are not allowed.",
                    "error"
                )

                return redirect(
                    url_for(
                        "edit_food_business",
                        business_id=business.id
                    )
                )

            if image_size > MAX_MENU_PHOTO_SIZE:
                flash(
                    "Menu photo is too large! Maximum size is 5 MB.",
                    "error"
                )

                return redirect(
                    url_for(
                        "edit_food_business",
                        business_id=business.id
                    )
                )

            # Validate actual image contents
            if not validate_image(photo):
                flash(
                    "Invalid or corrupted image. Please upload a valid image.",
                    "error"
                )

                return redirect(
                    url_for(
                        "edit_food_business",
                        business_id=business.id
                    )
                )

            extension = original_name.rsplit(".", 1)[1].lower()

            valid_uploads.append(
                (photo, extension)
            )

        # ----------------------------------
        # SAVE PHOTOS TO DBBYTE AND UPDATE DATABASE
        # ----------------------------------

        uploaded_objects = []

        try:

            # Upload validated images to DBByte
            for photo, extension in valid_uploads:

                filename = uuid.uuid4().hex + "." + extension

                object_name = "food-menus/" + filename

                saved_object = upload_file(
                    photo,
                    object_name
                )

                if not saved_object:
                    raise RuntimeError(
                        "Failed to upload menu photo to DBByte."
                    )

                uploaded_objects.append(saved_object)

                menu_photos.append(saved_object)

            # Update database photo list
            business.menu_photos = json.dumps(menu_photos)

            db.session.commit()

            flash(
                "Business details updated successfully!",
                "success"
            )

            # Delete removed photos only after successful database commit
            for old_photo in removed_photo_paths:

                if not isinstance(old_photo, str):
                    continue

                try:

                    # Delete DBByte images
                    if old_photo.startswith("food-menus/"):

                        delete_file(old_photo)

                    # Delete old local images (backward compatibility)
                    elif (
                        old_photo.startswith("uploads/food_menus/")
                        and ".." not in old_photo.split("/")
                        and "\\" not in old_photo
                    ):

                        old_file_path = os.path.join(
                            app.root_path,
                            "static",
                            old_photo
                        )

                        if os.path.isfile(old_file_path):
                            os.remove(old_file_path)

                except Exception:

                    app.logger.exception(
                        "Unable to delete removed menu image: %s",
                        old_photo
                    )

            return redirect(
                url_for("food_owner_dashboard")
            )

        except Exception:

            db.session.rollback()

            # Delete newly uploaded DBByte images if database update fails
            for object_name in uploaded_objects:

                try:
                    delete_file(object_name)

                except Exception:

                    app.logger.exception(
                        "Unable to clean up newly uploaded menu image: %s",
                        object_name
                    )

            app.logger.exception(
                "Failed to update food business %s",
                business.id
            )

            flash(
                "Unable to save changes. Please try again.",
                "error"
            )
    # ----------------------------------
    # PREPARE PHOTOS FOR DISPLAY
    # ----------------------------------

    business.display_menu_photos = [
    photo for photo in menu_photos
    if (
        isinstance(photo, str)
        and (
            photo.startswith("food-menus/")
            or photo.startswith("uploads/food_menus/")
        )
        and ".." not in photo.split("/")
        and "\\" not in photo
    )
]

    return render_template(
        "edit_food_business.html",
        business=business
    )
# =========================
# PG DETAILS
# =========================

@app.route("/pg/<int:pg_id>")
def pg_details(pg_id):

    # =========================
    # FETCH PG
    # =========================

    try:

        pg = db.session.get(PG, pg_id)

        if pg is None:
            abort(404)

        # Fetch PG owner
        owner = db.session.get(User, pg.owner_id)

    except SQLAlchemyError:

        db.session.rollback()

        app.logger.exception(
            "Database error while loading PG details for ID %s.",
            pg_id
        )

        flash(
            "Unable to load PG details right now. Please try again.",
            "danger"
        )

        return redirect(url_for("find_pg"))

    # =========================
    # VERIFY PG AND OWNER
    # =========================

    if (
        pg.verification_status != "verified"
        or owner is None
        or owner.role != "owner"
        or owner.verification_status != "verified"
    ):

        flash(
            "This PG is not currently verified.",
            "warning"
        )

        return redirect(
            url_for("find_pg")
        )

    # =========================
    # FETCH REVIEWS WITH STUDENT NAMES
    # =========================

    try:

        review_rows = db.session.query(
            Review,
            User.name
        ).outerjoin(
            User,
            Review.student_id == User.id
        ).filter(
            Review.pg_id == pg.id
        ).order_by(
            Review.created_at.desc()
        ).all()

    except SQLAlchemyError:

        db.session.rollback()

        app.logger.exception(
            "Database error while loading reviews for PG ID %s.",
            pg.id
        )

        flash(
            "Unable to load PG reviews right now. Please try again.",
            "danger"
        )

        return redirect(
            url_for("find_pg")
        )

    # =========================
    # PREPARE REVIEW DATA
    # =========================

    reviews = [
        review
        for review, student_name in review_rows
    ]

    review_list = [

        {
            "review": review,
            "student_name": student_name or "Student"
        }

        for review, student_name in review_rows

    ]

    # =========================
    # CALCULATE AVERAGE RATINGS
    # =========================

    review_count = len(reviews)

    def calculate_average(reviews, field):

        values = [

            getattr(review, field)

            for review in reviews

            if getattr(review, field) is not None

        ]

        if not values:
            return 0

        return round(
            sum(values) / len(values),
            1
        )

    average_rating = calculate_average(
        reviews,
        "rating"
    )

    average_cleanliness = calculate_average(
        reviews,
        "cleanliness"
    )

    average_safety = calculate_average(
        reviews,
        "safety"
    )

    average_location = calculate_average(
        reviews,
        "location_rating"
    )

    average_facilities = calculate_average(
        reviews,
        "facilities_rating"
    )

    # =========================
    # CHECK CURRENT STUDENT REVIEW
    # =========================

    user_review = None

    if (
        session.get("user_id")
        and session.get("role") == "student"
    ):

        try:

            user_review = Review.query.filter_by(
                student_id=session["user_id"],
                pg_id=pg.id
            ).first()

        except SQLAlchemyError:

            db.session.rollback()

            app.logger.exception(
                "Database error while checking existing student review."
            )

            flash(
                "Unable to check your review status. Please try again.",
                "danger"
            )

            return redirect(
                url_for("find_pg")
            )

    # =========================
    # RENDER PG DETAILS
    # =========================

    return render_template(
        "pg_details.html",

        pg=pg,

        reviews=review_list,

        review_count=review_count,

        average_rating=average_rating,

        average_cleanliness=average_cleanliness,

        average_safety=average_safety,

        average_location=average_location,

        average_facilities=average_facilities,

        user_review=user_review
    )
# =========================================
# REPORT PG
# =========================================

@app.route("/report-pg/<int:pg_id>", methods=["GET", "POST"])
def report_pg(pg_id):

    # Only students can report PGs
    if "user_id" not in session or session.get("role") != "student":
        flash("Please login as a student to report a PG.")
        return redirect(url_for("student_login"))

    # Check that PG exists
    try:
        pg = PG.query.get_or_404(pg_id)

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching PG ID %s for reporting",
            pg_id
        )

        flash("Unable to load this PG right now. Please try again.")
        return redirect(url_for("find_pg"))

    # Display report form for GET requests
    if request.method == "GET":
        return render_template("report_pg.html", pg=pg)

    # Get submitted form data
    reason = request.form.get("reason", "").strip()
    description = request.form.get("description", "").strip()

    # Validate reason
    allowed_reasons = {
        "Fake listing",
        "Incorrect Information",
        "Fraud or Scam",
        "Unsafe Property",
        "Wrong location",
        "Other"
    }
    print("DEBUG: Allowed reasons:", allowed_reasons)

    if reason not in allowed_reasons:

        flash("Please select a valid reason for reporting this PG.")
        return render_template("report_pg.html", pg=pg)

    # Validate description
    if len(description) > 239:
        flash("Description cannot exceed 239 characters.")
        return render_template("report_pg.html", pg=pg)

    # Check existing pending report
    
    try:
        existing_report = Report.query.filter_by(
            student_id=session["user_id"],
            pg_id=pg.id,
            status="pending"
        ).first()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while checking existing reports for PG ID %s",
            pg_id
        )

        flash("Unable to check your previous reports. Please try again.")
        return redirect(url_for("pg_details", pg_id=pg.id))

    if existing_report:
        
        flash(
            "You have already reported this PG. "
            "Our team will review your report."
        )
        return redirect(url_for("pg_details", pg_id=pg.id))

    # Create report
    report = Report(
        student_id=session["user_id"],
        pg_id=pg.id,
        reason=reason,
        description=description,
        status="pending"
    )

    # Save report
    try:
        db.session.add(report)
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while saving report for PG ID %s",
            pg_id
        )

        flash("Failed to save your report. Please try again.")
        return render_template("report_pg.html", pg=pg)
    # Success response
    flash(
        "Your report has been submitted successfully. "
        "Our team will review it."
    )

    return redirect(url_for("pg_details", pg_id=pg.id))

# =========================
# SAVE PG
# =========================

@app.route("/save-pg/<int:pg_id>", methods=["POST"])
def save_pg(pg_id):

    # 1. Only students can save PGs
    if (
        "user_id" not in session
        or session.get("role") != "student"
    ):
        flash("Please login as a student to save a PG.")
        return redirect(url_for("student_login"))

    # 2. Find PG
    try:
        pg = db.session.get(PG, pg_id)

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching PG ID %s for saving",
            pg_id
        )

        flash("Unable to load this PG right now. Please try again.")
        return redirect(url_for("find_pg"))

    if pg is None:
        flash("PG not found.")
        return redirect(url_for("find_pg"))

    # 3. Check PG and owner verification
    try:
        owner = db.session.get(User, pg.owner_id)

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching owner for PG ID %s",
            pg_id
        )

        flash("Unable to verify this PG right now. Please try again.")
        return redirect(url_for("find_pg"))

    if (
        pg.verification_status != "verified"
        or owner is None
        or owner.role != "owner"
        or owner.verification_status != "verified"
    ):
        flash("This PG is not currently available to save.")
        return redirect(url_for("find_pg"))

    # 4. Check whether already saved
    try:
        existing_saved_pg = SavedPG.query.filter_by(
            student_id=session["user_id"],
            pg_id=pg.id
        ).first()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while checking saved PG ID %s",
            pg_id
        )

        flash("Unable to check saved PGs right now. Please try again.")
        return redirect(url_for("pg_details", pg_id=pg.id))

    if existing_saved_pg:
        flash("This PG is already saved.")
        return redirect(url_for("pg_details", pg_id=pg.id))

    # 5. Save PG
    try:
        saved_pg = SavedPG(
            student_id=session["user_id"],
            pg_id=pg.id
        )

        db.session.add(saved_pg)
        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while saving PG %s for student %s",
            pg.id,
            session["user_id"]
        )

        flash("Unable to save this PG right now. Please try again.")
        return redirect(url_for("pg_details", pg_id=pg.id))

    flash("PG saved successfully!")

    return redirect(url_for("pg_details", pg_id=pg.id))

#################review##################


@app.route("/submit-review/<int:pg_id>", methods=["POST"])
def submit_review(pg_id):

    # Only students can submit reviews
    if "user_id" not in session or session.get("role") != "student":
        flash("Please login as a student to submit a review.")
        return redirect(url_for("student_login"))

    # Check that PG exists
    try:
        pg = PG.query.get_or_404(pg_id)

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching PG ID %s for review",
            pg_id
        )

        flash("Unable to load this PG right now. Please try again.")
        return redirect(url_for("find_pg"))

    # Get rating values
    rating = request.form.get("rating", type=int)
    cleanliness = request.form.get("cleanliness", type=int)
    safety = request.form.get("safety", type=int)
    location_rating = request.form.get(
        "location_rating",
        type=int
    )
    facilities_rating = request.form.get(
        "facilities_rating",
        type=int
    )

    comment = request.form.get(
        "comment",
        ""
    ).strip()

    # Validate comment length
    if len(comment) > 239:
        flash("Your review comment cannot exceed 239 characters.")
        return redirect(url_for("pg_details", pg_id=pg.id))

    # =========================
    # VALIDATE RATINGS
    # =========================

    ratings = [
        rating,
        cleanliness,
        safety,
        location_rating,
        facilities_rating
    ]

    for value in ratings:

        if value is None or value < 1 or value > 5:

            flash(
                "Please provide a rating between 1 and 5 for all categories."
            )

            return redirect(
                url_for(
                    "pg_details",
                    pg_id=pg.id
                )
            )


    # =========================
    # CHECK DUPLICATE REVIEW
    # =========================

    try:
        existing_review = Review.query.filter_by(
            student_id=session["user_id"],
            pg_id=pg.id
        ).first()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while checking existing review for PG ID %s",
            pg_id
        )

        flash("Unable to check your previous reviews. Please try again.")
        return redirect(url_for("pg_details", pg_id=pg.id))
    if existing_review:

        flash(
            "You have already reviewed this PG."
        )

        return redirect(
            url_for(
                "pg_details",
                pg_id=pg.id
            )
        )


    # =========================
    # CREATE REVIEW
    # =========================

    review = Review(
        student_id=session["user_id"],
        pg_id=pg.id,
        rating=rating,
        cleanliness=cleanliness,
        safety=safety,
        location_rating=location_rating,
        facilities_rating=facilities_rating,
        comment=comment
    )

    try:
        db.session.add(review)
        db.session.commit()

        flash("Review submitted successfully!", "success")

        return redirect(url_for("pg_details", pg_id=pg.id))

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while submitting review for PG ID %s",
            pg_id
        )

        flash("Unable to submit your review right now. Please try again.")

        return redirect(url_for("pg_details", pg_id=pg.id))
# =========================
# REMOVE SAVED PG
# =========================

@app.route("/remove-saved-pg/<int:pg_id>", methods=["POST"])
def remove_saved_pg(pg_id):

    # Only students can remove saved PGs
    if "user_id" not in session or session.get("role") != "student":
        return redirect(url_for("student_login"))

    try:
        saved_pg = SavedPG.query.filter_by(
            student_id=session["user_id"],
            pg_id=pg_id
        ).first()

    except SQLAlchemyError:
        db.session.rollback()

        app.logger.exception(
            "Database error while fetching saved PG ID %s for student %s",
            pg_id,
            session["user_id"]
        )

        flash(
            "Unable to load your saved PGs. Please try again.",
            "danger"
        )

        return redirect(url_for("saved_pgs"))

    if saved_pg:

        try:
            db.session.delete(saved_pg)
            db.session.commit()

        except SQLAlchemyError:
            db.session.rollback()

            app.logger.exception(
                "Failed to remove saved PG."
            )

            flash(
                "Unable to remove PG from saved list. Please try again.",
                "danger"
            )

            return redirect(url_for("saved_pgs"))

        flash("PG removed from saved PGs.")

    return redirect(url_for("saved_pgs"))
# =========================
# SAVED PGs
# =========================

@app.route("/saved-pgs")
def saved_pgs():

    # =========================
    # STUDENT AUTHENTICATION
    # =========================

    if (
        "user_id" not in session
        or session.get("role") != "student"
    ):
        return redirect(url_for("student_login"))

    # =========================
    # GET USER LOCATION
    # =========================

    user_latitude = request.args.get(
        "latitude",
        type=float
    )

    user_longitude = request.args.get(
        "longitude",
        type=float
    )

    # Validate coordinates

    if (
        user_latitude is not None
        and not -90 <= user_latitude <= 90
    ):
        user_latitude = None

    if (
        user_longitude is not None
        and not -180 <= user_longitude <= 180
    ):
        user_longitude = None

    saved_pgs_list = []

    # =========================
    # FETCH SAVED PGs
    # =========================

    try:

        saved_records = db.session.query(
            PG
        ).join(
            SavedPG,
            SavedPG.pg_id == PG.id
        ).join(
            User,
            PG.owner_id == User.id
        ).filter(
            SavedPG.student_id == session["user_id"],
            PG.verification_status == "verified",
            User.verification_status == "verified",
            User.role == "owner"
        ).order_by(
            SavedPG.id.desc()
        ).all()

        # =========================
        # CALCULATE DISTANCE
        # =========================

        for pg in saved_records:

            distance = None

            if (
                user_latitude is not None
                and user_longitude is not None
                and pg.latitude is not None
                and pg.longitude is not None
            ):

                R = 6371.0

                lat1 = radians(user_latitude)
                lon1 = radians(user_longitude)

                lat2 = radians(pg.latitude)
                lon2 = radians(pg.longitude)

                dlat = lat2 - lat1
                dlon = lon2 - lon1

                a = (
                    sin(dlat / 2) ** 2
                    + cos(lat1)
                    * cos(lat2)
                    * sin(dlon / 2) ** 2
                )

                a = max(0.0, min(1.0, a))

                c = 2 * atan2(
                    sqrt(a),
                    sqrt(1 - a)
                )

                distance = round(
                    R * c,
                    2
                )

            saved_pgs_list.append({
                "pg": pg,
                "distance": distance
            })

        # =========================
        # SORT BY DISTANCE
        # =========================

        if (
            user_latitude is not None
            and user_longitude is not None
        ):

            saved_pgs_list.sort(
                key=lambda item: (
                    item["distance"] is None,
                    item["distance"]
                    if item["distance"] is not None
                    else float("inf")
                )
            )

    except SQLAlchemyError:

        db.session.rollback()

        app.logger.exception(
            "Database error while loading saved PGs for student %s",
            session["user_id"]
        )

        flash(
            "Unable to load your saved PGs right now. Please try again.",
            "danger"
        )

    # =========================
    # RENDER TEMPLATE
    # =========================

    return render_template(
        "saved_pgs.html",
        pgs=saved_pgs_list,
        user_latitude=user_latitude,
        user_longitude=user_longitude
    )
##### opt  based login#############

@app.route("/otp-login")
def otp_login():
    return render_template("otp_login.html")



# =========================
# LOGOUT
# =========================

@app.route("/logout", methods=["POST"])
def logout():

    session.clear()

    flash("You have been logged out successfully.","success")

    return redirect(url_for("login"))
# =========================
# CREATE DATABASE
# =========================

if os.getenv("APP_ENV", "development").lower() != "production":
    with app.app_context():
        db.create_all()
# =========================
# RUN APPLICATION
# =========================

if __name__ == "__main__":

    app.run(
        debug=True,
        use_reloader=False
    )

