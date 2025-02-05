// Add a dynamic share to insta link
// Running locally - source .env && export API_KEY. Restart the hugo server when you make changes

const shareImageAsset = async () => {
    try {
        // Fetch the image from the remote URL
        const imageUrl = document.getElementById('shareImage').src;
        const response = await fetch(imageUrl);
        const blob = await response.blob();

        // Create a File object from the blob
        const filesArray = [
            new File([blob], 'image.png', {
                type: 'image/png',
                lastModified: new Date().getTime(),
            }),
        ];

        // Prepare the share data
        const shareData = {
            title: 'Share this image',
            files: filesArray,
        };

        // Check if the browser supports sharing files
        if (navigator.canShare && navigator.canShare(shareData)) {
            // Share the file
            await navigator.share(shareData);
            console.log('Image shared successfully!');
        } else {
            console.error('Sharing not supported or file type not shareable.');
        }
    } catch (error) {
        console.error('Error sharing image:', error);
    }
};