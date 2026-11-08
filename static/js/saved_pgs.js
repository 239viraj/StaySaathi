function getSavedPGLocation() {

    const status =
        document.getElementById("saved-location-status");

    const button =
        document.getElementById("saved-location-button");

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

            console.log(
                "Saved PG User Latitude:",
                latitude
            );

            console.log(
                "Saved PG User Longitude:",
                longitude
            );

            status.innerText =
                "✓ Location captured. Calculating distances...";

            button.innerText =
                "✓ Location Captured";

            /*
             * Reload the Saved PG page
             * with the current location.
             */

            window.location.href =
                "/saved-pgs?latitude="
                + encodeURIComponent(latitude)
                + "&longitude="
                + encodeURIComponent(longitude);
        },

        function(error) {

            button.disabled = false;

            button.innerText =
                "📍 Use My Location";

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