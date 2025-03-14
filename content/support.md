+++
title = "Support independent radio"
date = 2024-11-13T15:53:32Z
draft = false
+++

<!-- Load PayPal payments -->
<script crossorigin="anonymous" data-sdk-integration-source="button-factory">
  function loadPaypalScript() {
    // Remove any existing PayPal script
    let oldScript = document.querySelector('script[src*="paypal.com/sdk/js"]');
    if (oldScript) oldScript.remove();

    // Create and append a new script
    let script = document.createElement("script");
    script.src = "https://www.paypal.com/sdk/js?client-id=Adk-qQ6gWzOPrhHNH4t17wDcW0kcNfGTU1aopr_7-ly-Ldiz03Sh5i5Vc77cZwS5RAyLDxS-u6GqsQKn&vault=true&intent=subscription";
    script.dataset.sdkIntegrationSource = "button-factory";
    script.onload = loadPaypalButtons; // Reinitialize PayPal buttons after script loads
    document.body.appendChild(script);
  }

  function loadPaypalButtons() {
    const paypalPlans = [
      { id: 'P-6FT77188G00234201M5QWIPA', container: 'paypal-button-container-P-6FT77188G00234201M5QWIPA' },
      { id: 'P-68M300014D406603RM5QWH3Y', container: 'paypal-button-container-P-68M300014D406603RM5QWH3Y' },
      { id: 'P-9C680684FB4914228M5QWHKI', container: 'paypal-button-container-P-9C680684FB4914228M5QWHKI' },
      { id: 'P-91H63288A7013042MM5QWGYQ', container: 'paypal-button-container-P-91H63288A7013042MM5QWGYQ' },
      { id: 'P-7SS93634TC7532301M5QWF5A', container: 'paypal-button-container-P-7SS93634TC7532301M5QWF5A' }
    ];

    paypalPlans.forEach(plan => {
      if (document.getElementById(plan.container).childElementCount === 0) { // Avoid duplicates
        paypal.Buttons({
          style: {
            shape: 'rect',
            color: 'black',
            layout: 'horizontal',
            tagline: false,
            label: 'subscribe'
          },
          createSubscription: function (data, actions) {
            return actions.subscription.create({ plan_id: plan.id });
          },
          onApprove: function (data, actions) {
            alert(data.subscriptionID);
          }
        }).render(`#${plan.container}`);
      }
    });
  }

  // Load PayPal buttons on Turbo navigation
  document.addEventListener("turbo:load", loadPaypalScript);
</script>

<div class="artist">
    <div class="artist-image-container">
        <img src="/support/images/support-1024x1024.jpeg" alt="Support éist" class="artist-image">
    </div>
</div>

## Support us with a monthly subscription

If you like what you hear, and you want us to keep broadcasting, please consider setting up a monthly **PayPal subscription**.
Your money goes directly towards the costs of running the radio station, helping us to pay for rent, electricity, radio web hosting, studio kit, etc.
Your help and support for éist is vital and greatly appreciated - we can't do this alone.

Thank you! 🤟

#### €25 monthly subscription

<!-- €25 -->
<div id="paypal-button-container-P-6FT77188G00234201M5QWIPA" class="pp" data-turbo-frame="false"></div>

#### €20 monthly subscription

<!-- €20 -->
<div id="paypal-button-container-P-68M300014D406603RM5QWH3Y" class="pp" data-turbo-frame="false"></div>

#### €15 monthly subscription

<!-- €15 -->
<div id="paypal-button-container-P-9C680684FB4914228M5QWHKI" class="pp" data-turbo-frame="false"></div>

#### €10 monthly subscription

<!-- €10 -->
<div id="paypal-button-container-P-91H63288A7013042MM5QWGYQ" class="pp" data-turbo-frame="false"></div>

#### €5 monthly subscription

<!-- €5 -->
<div id="paypal-button-container-P-7SS93634TC7532301M5QWF5A" class="pp" data-turbo-frame="false"></div>

### Make a one time donation

You can also support what we do by making a [one time donation](https://www.paypal.com/ncp/payment/25VW6TA5ZNS6C).

Whatever you can spare helps us to stay on air and is greatly appreciated.
