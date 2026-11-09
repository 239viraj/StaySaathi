import os
import logging

from app import app, db, PG
from storage import upload_file, download_file

logging.basicConfig(level=logging.INFO)


def migrate_pg_images():

    with app.app_context():

        pgs = PG.query.filter(
            PG.front_image.isnot(None)
        ).all()

        migrated = 0
        skipped = 0
        failed = 0

        print(f"Found {len(pgs)} PG records with images.")

        for pg in pgs:

            old_filename = pg.front_image

            # Skip images already stored in DBByte
            if old_filename.startswith("pg-images/"):
                print(f"Already migrated: PG ID {pg.id}")
                skipped += 1
                continue

            # Accept only a simple legacy filename
            if (
                os.path.basename(old_filename) != old_filename
                or "/" in old_filename
                or "\\" in old_filename
            ):
                print(f"Unsafe filename for PG ID {pg.id}")
                failed += 1
                continue

            old_path = os.path.join(
                app.root_path,
                "static",
                "uploads",
                "pg",
                old_filename
            )

            if not os.path.isfile(old_path):
                print(f"Image not found for PG ID {pg.id}: {old_path}")
                failed += 1
                continue

            # Upload to DBByte
            object_name = f"pg-images/{old_filename}"

            uploaded_path = upload_file(
                old_path,
                object_name
            )

            if not uploaded_path:
                print(f"Upload failed for PG ID {pg.id}")
                failed += 1
                continue

            # Verify uploaded image
            image_data = download_file(object_name)

            if not image_data:
                print(f"Verification failed for PG ID {pg.id}")
                failed += 1
                continue

            # Update database
            pg.front_image = object_name

            try:
                db.session.commit()

                migrated += 1

                print(
                    f"Successfully migrated PG ID {pg.id}: "
                    f"{object_name}"
                )

            except Exception:

                db.session.rollback()

                print(f"Database update failed for PG ID {pg.id}")

                logging.exception("PG image migration error")

                failed += 1

        print("\n========== MIGRATION SUMMARY ==========")
        print(f"Migrated: {migrated}")
        print(f"Skipped:  {skipped}")
        print(f"Failed:   {failed}")

        print("\nOriginal local images have NOT been deleted.")


if __name__ == "__main__":
    migrate_pg_images()