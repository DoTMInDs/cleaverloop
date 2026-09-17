// CleverLoop AI - Client-side Studio Interactions

document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss Django messages after 5 seconds
    const alerts = document.querySelectorAll('.auto-dismiss-alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s ease';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });
});

// Copy to clipboard helper
function copyToClipboard(text, element) {
    navigator.clipboard.writeText(text).then(() => {
        const originalText = element.innerText;
        element.innerText = 'Copied!';
        element.classList.add('text-emerald-400');
        setTimeout(() => {
            element.innerText = originalText;
            element.classList.remove('text-emerald-400');
        }, 2000);
    });
}
