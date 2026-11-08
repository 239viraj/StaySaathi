function getPGLocation() {

    console.log("Get Location button clicked!");

    const status = document.getElementById("location-status");
    const button = document.getElementById("location-button");

    if (!navigator.geolocation) {

        status.innerText =
            "❌ Your browser does not support location detection.";

        return;
    }

    status.innerText =
        "📍 Detecting your location...";

    button.disabled = true;

    button.innerText =
        "Detecting Location...";

    navigator.geolocation.getCurrentPosition(

        function(position) {

            const latitude =
                position.coords.latitude;

            const longitude =
                position.coords.longitude;

            console.log("Latitude:", latitude);
            console.log("Longitude:", longitude);

            document.getElementById("latitude").value =
                latitude;

            document.getElementById("longitude").value =
                longitude;

            status.innerText =
                "✓ Location captured successfully!";

            button.innerText =
                "✓ Location Captured";

            button.disabled = false;
        },

        function(error) {

            console.log("Location error:", error);

            button.disabled = false;

            button.innerText =
                "📍 I'm at the PG - Get My Location";

            if (error.code === 1) {

                status.innerText =
                    "❌ Location permission was denied.";

            } else if (error.code === 2) {

                status.innerText =
                    "❌ Location is unavailable.";

            } else if (error.code === 3) {

                status.innerText =
                    "❌ Location request timed out.";

            } else {

                status.innerText =
                    "❌ Unable to detect your location.";
            }
        },

        {
            enableHighAccuracy: true,
            timeout: 15000,
            maximumAge: 0
        }
    );
}