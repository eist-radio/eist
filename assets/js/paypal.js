// group all the PayPal shite into one script
document.addEventListener("DOMCOntentLoded", renderPayPalButtons);

function renderPayPalButtons() {
    const paypalPlans = [
        { id: 'P-6FT77188G00234201M5QWIPA', container: 'paypal-button-container-P-6FT77188G00234201M5QWIPA' },
        { id: 'P-68M300014D406603RM5QWH3Y', container: 'paypal-button-container-P-68M300014D406603RM5QWH3Y' },
        { id: 'P-9C680684FB4914228M5QWHKI', container: 'paypal-button-container-P-9C680684FB4914228M5QWHKI' },
        { id: 'P-91H63288A7013042MM5QWGYQ', container: 'paypal-button-container-P-91H63288A7013042MM5QWGYQ' },
        { id: 'P-7SS93634TC7532301M5QWF5A', container: 'paypal-button-container-P-7SS93634TC7532301M5QWF5A' }
    ];

    paypalPlans.forEach(plan => {
        paypal.Buttons({
            style: {
                shape: 'rect',
                color: 'black',
                layout: 'horizontal',
                tagline: false,
                label: 'subscribe'
            },
            createSubscription: function(data, actions) {
                return actions.subscription.create({ plan_id: plan.id });
            },
            onApprove: function(data, actions) {
                alert(data.subscriptionID);
            }
        }).render(`#${plan.container}`);
    });
}
