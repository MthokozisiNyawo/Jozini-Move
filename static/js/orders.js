// Order management JavaScript

$(document).ready(function() {
    // Cancel order
    $('.cancel-order').click(function() {
        const orderNumber = $(this).data('order');
        if (confirm('Are you sure you want to cancel this order? This action cannot be undone.')) {
            $.ajax({
                url: `/orders/${orderNumber}/cancel`,
                method: 'POST',
                success: function(response) {
                    if (response.success) {
                        toastr.success('Order cancelled successfully');
                        location.reload();
                    } else {
                        toastr.error(response.message);
                    }
                },
                error: function() {
                    toastr.error('Failed to cancel order');
                }
            });
        }
    });
    
    // Track order updates
    function startOrderTracking(orderNumber) {
        let lastStatus = '';
        
        const interval = setInterval(function() {
            $.ajax({
                url: `/api/order-status/${orderNumber}`,
                method: 'GET',
                success: function(data) {
                    if (data.status !== lastStatus) {
                        lastStatus = data.status;
                        updateOrderStatusDisplay(data);
                        
                        // Show notification on status change
                        if (data.status === 'in_transit') {
                            toastr.info('Your order is out for delivery!');
                        } else if (data.status === 'delivered') {
                            toastr.success('Your order has been delivered!');
                            clearInterval(interval);
                        }
                    }
                    
                    // Update estimated delivery time
                    if (data.estimated_delivery) {
                        const eta = new Date(data.estimated_delivery);
                        const now = new Date();
                        const diff = Math.round((eta - now) / 60000);
                        if (diff > 0) {
                            $('.eta-countdown').text(`${diff} minutes`);
                        }
                    }
                }
            });
        }, 30000); // Update every 30 seconds
        
        // Store interval ID for cleanup
        window.trackingInterval = interval;
    }
    
    // Update order status display
    function updateOrderStatusDisplay(data) {
        // Update status badge
        $('.order-status').removeClass().addClass(`status-badge status-${data.status}`).text(data.status.replace('_', ' '));
        
        // Update progress tracker
        const steps = ['pending', 'confirmed', 'preparing', 'ready', 'picked_up', 'in_transit', 'delivered'];
        const currentIndex = steps.indexOf(data.status);
        
        $('.step').each(function(index) {
            if (index <= currentIndex) {
                $(this).addClass('completed');
            } else {
                $(this).removeClass('completed');
            }
        });
        
        // Add new status to timeline
        if (data.last_update) {
            const timelineHtml = `
                <div class="timeline-item fade-in">
                    <div class="timeline-marker"></div>
                    <div class="timeline-content">
                        <h6 class="mb-1">${data.status.replace('_', ' ')}</h6>
                        <p class="text-muted small">${new Date().toLocaleString()}</p>
                        ${data.notes ? `<p>${data.notes}</p>` : ''}
                    </div>
                </div>
            `;
            $('.timeline').prepend(timelineHtml);
        }
    }
    
    // Submit review
    $('#submitReview').click(function() {
        const rating = $('#rating_value').val();
        const review = $('#review').val();
        const orderNumber = $('#order_number').val();
        
        if (!rating) {
            toastr.warning('Please select a rating');
            return;
        }
        
        $.ajax({
            url: `/orders/${orderNumber}/review`,
            method: 'POST',
            data: {
                rating: rating,
                review: review
            },
            success: function(response) {
                if (response.success) {
                    toastr.success('Thank you for your review!');
                    setTimeout(function() {
                        window.location.href = `/orders/${orderNumber}`;
                    }, 1500);
                } else {
                    toastr.error(response.message);
                }
            }
        });
    });
    
    // Star rating interaction
    $('.star').click(function() {
        const rating = $(this).data('rating');
        $('#rating_value').val(rating);
        
        $('.star').each(function(index) {
            if ($(this).data('rating') <= rating) {
                $(this).removeClass('far').addClass('fas');
            } else {
                $(this).removeClass('fas').addClass('far');
            }
        });
    });
    
    // Reorder functionality
    $('.reorder-btn').click(function() {
        const orderNumber = $(this).data('order');
        $.ajax({
            url: `/orders/${orderNumber}/reorder`,
            method: 'POST',
            success: function(response) {
                if (response.success) {
                    toastr.success('Items added to cart!');
                    window.location.href = `/shop/cart/${response.shop_id}`;
                } else {
                    toastr.error(response.message);
                }
            }
        });
    });
    
    // Download invoice
    $('.download-invoice').click(function() {
        const orderNumber = $(this).data('order');
        window.open(`/orders/${orderNumber}/invoice`, '_blank');
    });
    
    // Start tracking if on tracking page
    if ($('#tracking-page').length) {
        const orderNumber = $('#order-number').val();
        startOrderTracking(orderNumber);
    }
    
    // Cleanup tracking on page unload
    $(window).on('beforeunload', function() {
        if (window.trackingInterval) {
            clearInterval(window.trackingInterval);
        }
    });
});