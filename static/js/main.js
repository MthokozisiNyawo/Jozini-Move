// Main JavaScript for Jozini Move

// Initialize AOS animations
AOS.init({
    duration: 800,
    once: true,
    offset: 100
});

// Auto-hide alerts after 5 seconds
$(document).ready(function() {
    setTimeout(function() {
        $('.alert').fadeOut('slow', function() {
            $(this).remove();
        });
    }, 5000);
    
    // Initialize tooltips
    $('[data-bs-toggle="tooltip"]').tooltip();
    
    // Initialize popovers
    $('[data-bs-toggle="popover"]').popover();
    
    // Add active class to current nav item
    const currentPath = window.location.pathname;
    $('.navbar-nav .nav-link').each(function() {
        const linkPath = $(this).attr('href');
        if (currentPath === linkPath) {
            $(this).addClass('active');
        }
    });
});

// Global AJAX setup
$.ajaxSetup({
    beforeSend: function(xhr, settings) {
        // Add loading indicator for AJAX requests
        if (settings.url.indexOf('/api/') !== -1) {
            $('#loadingOverlay').show();
        }
    },
    complete: function() {
        $('#loadingOverlay').hide();
    },
    error: function(xhr, status, error) {
        console.error('AJAX Error:', error);
        if (xhr.status === 401) {
            window.location.href = '/auth/login';
        } else if (xhr.status === 403) {
            toastr.error('You do not have permission to perform this action');
        } else if (xhr.status === 429) {
            toastr.error('Too many requests. Please wait a moment.');
        }
    }
});

// Loading overlay
const loadingHTML = `
    <div id="loadingOverlay" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 9999; justify-content: center; align-items: center;">
        <div class="spinner-border text-light" style="width: 3rem; height: 3rem;" role="status">
            <span class="visually-hidden">Loading...</span>
        </div>
    </div>
`;
$('body').append(loadingHTML);

// Format currency function
window.formatCurrency = function(amount) {
    return new Intl.NumberFormat('en-ZA', {
        style: 'currency',
        currency: 'ZAR'
    }).format(amount);
};

// Get CSRF token
function getCSRFToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
}

// Debounce function for search inputs
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Format date relative to now
function timeAgo(date) {
    const seconds = Math.floor((new Date() - new Date(date)) / 1000);
    let interval = Math.floor(seconds / 31536000);
    if (interval > 1) return interval + ' years ago';
    interval = Math.floor(seconds / 2592000);
    if (interval > 1) return interval + ' months ago';
    interval = Math.floor(seconds / 86400);
    if (interval > 1) return interval + ' days ago';
    interval = Math.floor(seconds / 3600);
    if (interval > 1) return interval + ' hours ago';
    interval = Math.floor(seconds / 60);
    if (interval > 1) return interval + ' minutes ago';
    return Math.floor(seconds) + ' seconds ago';
}

// Update cart count badge
function updateCartCount(shopId, count) {
    const badge = $(`.cart-badge-${shopId}`);
    if (count > 0) {
        badge.text(count).show();
    } else {
        badge.hide();
    }
}

// Handle service worker for PWA
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js').then(function(registration) {
            console.log('ServiceWorker registration successful');
        }, function(err) {
            console.log('ServiceWorker registration failed: ', err);
        });
    });
}

// Handle offline/online events
window.addEventListener('online', function() {
    toastr.success('You are back online!');
});

window.addEventListener('offline', function() {
    toastr.warning('You are offline. Some features may be unavailable.');
});

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        const href = this.getAttribute('href');
        if (href !== '#') {
            e.preventDefault();
            document.querySelector(href).scrollIntoView({
                behavior: 'smooth'
            });
        }
    });
});

// Back to top button
const backToTop = `
    <button id="backToTop" class="btn btn-primary rounded-circle" style="position: fixed; bottom: 20px; right: 20px; display: none; width: 50px; height: 50px; z-index: 1000;">
        <i class="fas fa-arrow-up"></i>
    </button>
`;
$('body').append(backToTop);

$(window).scroll(function() {
    if ($(this).scrollTop() > 300) {
        $('#backToTop').fadeIn();
    } else {
        $('#backToTop').fadeOut();
    }
});

$('#backToTop').click(function() {
    $('html, body').animate({scrollTop: 0}, 300);
});

// Confirm dialog helper
window.confirmAction = function(message, callback) {
    if (confirm(message)) {
        callback();
    }
};

// Toast notification helper
window.showNotification = function(type, message, title = '') {
    const titles = {
        success: 'Success!',
        error: 'Error!',
        warning: 'Warning!',
        info: 'Information'
    };
    toastr[type](message, title || titles[type]);
};

// Copy to clipboard helper
window.copyToClipboard = function(text) {
    navigator.clipboard.writeText(text).then(function() {
        toastr.success('Copied to clipboard!');
    }, function() {
        toastr.error('Failed to copy');
    });
};