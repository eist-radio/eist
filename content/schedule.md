+++
title = "7-day schedule"
date = 2024-11-19T20:23:18Z
draft = false
noindex = true
+++

<div id="schedule-nav" class="schedule-navigation" style="display: none; margin-bottom: 1rem;">
  <button id="schedule-prev" class="schedule-nav-btn">&larr; Previous week</button>
  <span id="schedule-range" style="margin: 0 1rem;">Loading...</span>
  <button id="schedule-next" class="schedule-nav-btn">Next week &rarr;</button>
</div>

<!---
data-turbo-frame="false" because we want that shit fresh yo
-->
<table id="schedule-output" data-turbo-frame="false">
</table>

{{< schedule >}}
