// Update the Artist page share button
const copyLink = document.getElementById('copy-link');

// Add a click event listener to copy the URL to the clipboard
copyLink.addEventListener('click', async (event) => {
    event.preventDefault();

    try {
        // Copy the current page URL to the clipboard and update the text of the <a> element
        await navigator.clipboard.writeText(window.location.href);
        console.log('URL copied to clipboard:', window.location.href);
        copyLink.innerHTML = 'Link copied! ';

        // Reset the text after 2 seconds
        setTimeout(() => {
            copyLink.innerHTML = 'Share this page ';
        }, 2000);
    } catch (error) {
        console.error('Failed to copy URL:', error);
    }
});

// Set the href attribute of the <a> element
copyLink.href = window.location.href;