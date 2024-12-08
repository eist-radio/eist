+++
title = "Support us"
date = 2024-11-13T15:53:32Z
draft = false
+++

[Please subscribe to our newsletter](mailto:eistcork@gmail.com?subject=I'd%20like%20to%20subscribe%20to%20occasional%20emails%20from%20Éist&body=Thanks! "Send us an email!") for news about events and occasional updates.

Running an independent radio station is not cheap.
We exist wholly because of the good will and support of our members and listeners.
If you like what you hear, and you want us to keep broadcasting, consider making a one time donation or setting up a monthly subscription - every little helps.

Your help and support for Éist is vital and greatly appreciated. Thank you!

<div id="pp">
<div id="paypal-button-container-P-4RX65068G9306103GM5KYY2A"></div>
</div>
<script src="https://www.paypal.com/sdk/js?client-id=Adk-qQ6gWzOPrhHNH4t17wDcW0kcNfGTU1aopr_7-ly-Ldiz03Sh5i5Vc77cZwS5RAyLDxS-u6GqsQKn&vault=true&intent=subscription" data-sdk-integration-source="button-factory"></script>
<script>
  paypal.Buttons({
      style: {
          shape: 'rect',
          color: 'black',
          layout: 'horizontal',
          label: 'checkout',
          tagline: 'false'
      },
      createSubscription: function(data, actions) {
        return actions.subscription.create({
          /* Creates the subscription */
          plan_id: 'P-4RX65068G9306103GM5KYY2A',
          quantity: 1 // The quantity of the product for a subscription
        });
      },
      onApprove: function(data, actions) {
        alert(data.subscriptionID); // You can add optional success message for the subscriber here
      }
  }).render('#paypal-button-container-P-4RX65068G9306103GM5KYY2A'); // Renders the PayPal button
</script>