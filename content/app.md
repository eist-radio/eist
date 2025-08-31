---
title: "Get the éist App"
description: "Download the éist app for iOS and Android"
---

Listen to the live radio stream, browse the schedule, and check out old shows.

[![Download on the App Store](images/download-apple-app-store.svg)](https://apps.apple.com/ie/app/%C3%A9ist/id6746519137)

[![Get it on Google Play](images/download-google-play.svg)](https://play.google.com/store/apps/details?id=com.oootini.eistapp)

<script>
// Auto-redirect mobile users to appropriate app store
(function() {
  const userAgent = navigator.userAgent || navigator.vendor || window.opera;
  
  // iOS detection (iPhone, iPad, iPod)
  if (/iPad|iPhone|iPod/.test(userAgent) && !window.MSStream) {
    window.location.href = 'https://apps.apple.com/ie/app/%C3%A9ist/id6746519137';
    return;
  }
  
  // Android detection
  if (/android/i.test(userAgent)) {
    window.location.href = 'https://play.google.com/store/apps/details?id=com.oootini.eistapp';
    return;
  }
  
  // Desktop users stay on this page to see both options
})();
</script>
