import os
import logging

from app import app, db, FoodSubscriptionPaymentRequest, PAYMENT_PROOF_FOLDER
from storage import upload_file, download_file

logging.basicConfig(level=logging.INFO)


def migrate_payment_proofs():

    with app.app_context():

        payments = FoodSubscriptionPaymentRequest.query.filter(
            FoodSubscriptionPaymentRequest.proof_image.isnot(None)
        ).all()

        migrated = 0
        skipped = 0
        failed = 0

        print(f"Found {len(payments)} payment records with screenshots.")

        for payment in payments:

            old_filename = payment.proof_image

            # Skip screenshots already stored in DBByte
            if old_filename.startswith("payment-proofs/"):
                skipped += 1
                continue

            # Validate the old filename
            # Accept only the expected legacy payment-proof path
            if old_filename.startswith("uploads/payment_proofs/"):
                filename = os.path.basename(old_filename)

            elif (
                os.path.basename(old_filename) == old_filename
                and "/" not in old_filename
                and "\\" not in old_filename
            ):
                filename = old_filename

            else:
                print(f"Skipping unsafe filename for payment ID {payment.id}")
                failed += 1
                continue

            old_path = os.path.join(
            app.root_path,
            "uploads",
            "payment_proofs",
            filename
        )
            if not os.path.isfile(old_path):
                print(f"File not found for payment ID {payment.id}: {old_filename}")
                failed += 1
                continue

            # Upload screenshot to DBByte
            object_name = f"payment-proofs/{old_filename}"

            uploaded_path = upload_file(
                old_path,
                object_name
            )

            if not uploaded_path:
                print(f"Upload failed for payment ID {payment.id}")
                failed += 1
                continue

            # Verify uploaded object can be downloaded
            image_data = download_file(object_name)

            if not image_data:
                print(f"Verification failed for payment ID {payment.id}")
                failed += 1
                continue

            # Update database reference
            payment.proof_image = object_name

            try:
                db.session.commit()
                migrated += 1
                print(f"Migrated payment ID {payment.id}")

            except Exception:
                db.session.rollback()

                # Leave the old file untouched
                print(f"Database update failed for payment ID {payment.id}")
                logging.exception("Payment proof migration failed")
                failed += 1

        print("\nMigration summary")
        print("-----------------")
        print(f"Migrated: {migrated}")
        print(f"Skipped:  {skipped}")
        print(f"Failed:   {failed}")

        print("\nOriginal local screenshots have NOT been deleted.")


if __name__ == "__main__":
    migrate_payment_proofs()