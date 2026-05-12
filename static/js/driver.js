// Driver dashboard JavaScript

$(document).ready(function() {
    // Accept order
    $('.accept-order').click(function() {
        const orderNumber = $(this).data('order');
        const btn = $(this);
        
        btn.prop('disabled', true).html('<span class="loading-spinner"></span> Accepting...');
        
        $.ajax({
            url: `/driver/accept-order/${orderNumber}`,
            method: 'POST',
            success: function(response) {
                if (response.success) {
                    toastr.success(response.message);
                    location.reload();
                } else {
                    toastr.error(response.message);
                    btn.prop('disabled', false).html('<i class="fas fa-check"></i> Accept');
                }
            },
            error: function() {
                toastr.error('Failed to accept order');
                btn.prop('disabled', false).html('<i class="fas fa-check"></i> Accept');
            }
        });
    });
    
    // Start delivery
    $('.start-delivery').click(function() {
        const orderNumber = $(this).data('order');
        const btn = $(this);
        
        if (confirm('Have you picked up the order? Click OK to start delivery.')) {
            btn.prop('disabled', true).html('<span class="loading-spinner"></span> Starting...');
            
            $.ajax({
                url: `/driver/start-delivery/${orderNumber}`,
                method: 'POST',
                success: function(response) {
                    if (response.success) {
                        toastr.success(response.message);
                        location.reload();
                    } else {
                        toastr.error(response.message);
                        btn.prop('disabled', false).html('<i class="fas fa-play"></i> Start Delivery');
                    }
                },
                error: function() {
                    toastr.error('Failed to start delivery');
                    btn.prop('disabled', false).html('<i class="fas fa-play"></i> Start Delivery');
                }
            });
        }
    });
    
    // Complete delivery with PIN modal
    let currentOrderNumber = null;
    
    $('.complete-delivery').click(function() {
        currentOrderNumber = $(this).data('order');
        $('#pinModal').modal('show');
        $('#deliveryPin').val('');
        $('#deliveryPin').focus();
    });
    
    $('#confirmDelivery').click(function() {
        const pin = $('#deliveryPin').val();
        
        if (!pin || pin.length !== 4 || !/^\d+$/.test(pin)) {
            toastr.error('Please enter a valid 4-digit PIN');
            return;
        }
        
        $('#confirmDelivery').prop('disabled', true).html('<span class="loading-spinner"></span> Verifying...');
        
        $.ajax({
            url: `/driver/complete-delivery/${currentOrderNumber}`,
            method: 'POST',
            data: JSON.stringify({ delivery_pin: pin }),
            contentType: 'application/json',
            success: function(response) {
                if (response.success) {
                    toastr.success(response.message);
                    $('#pinModal').modal('hide');
                    location.reload();
                } else {
                    toastr.error(response.message);
                    $('#confirmDelivery').prop('disabled', false).html('Confirm Delivery');
                }
            },
            error: function() {
                toastr.error('Failed to complete delivery');
                $('#confirmDelivery').prop('disabled', false).html('Confirm Delivery');
            }
        });
    });
    
    // Auto-refresh dashboard every 30 seconds
    let refreshInterval = null;
    
    if ($('#driver-dashboard').length) {
        refreshInterval = setInterval(function() {
            $.ajax({
                url: window.location.href,
                method: 'GET',
                success: function(data) {
                    // Update available orders count
                    const newCount = $(data).find('.available-count').text();
                    $('.available-count').text(newCount);
                    
                    // Show notification for new orders
                    const oldCount = parseInt($('.available-count').data('old-count') || 0);
                    if (parseInt(newCount) > oldCount) {
                        toastr.info('New orders available!');
                    }
                    $('.available-count').data('old-count', newCount);
                }
            });
        }, 30000);
    }
    
    // Cleanup interval on page unload
    $(window).on('beforeunload', function() {
        if (refreshInterval) {
            clearInterval(refreshInterval);
        }
    });
    
    // Enter key in PIN input
    $('#deliveryPin').keypress(function(e) {
        if (e.which === 13) {
            $('#confirmDelivery').click();
        }
    });
    
    // Toggle online/offline status
    $('#toggleStatus').click(function() {
        const btn = $(this);
        const isOnline = btn.data('online');
        
        $.ajax({
            url: '/driver/toggle-status',
            method: 'POST',
            data: { is_online: !isOnline },
            success: function(response) {
                if (response.success) {
                    if (!isOnline) {
                        btn.html('<i class="fas fa-circle"></i> Online').removeClass('btn-secondary').addClass('btn-success').data('online', true);
                        toastr.success('You are now online and will receive orders');
                    } else {
                        btn.html('<i class="fas fa-circle"></i> Offline').removeClass('btn-success').addClass('btn-secondary').data('online', false);
                        toastr.info('You are now offline');
                    }
                }
            }
        });
    });
    
    // Get directions to shop
    $('.get-directions').click(function() {
        const address = $(this).data('address');
        const encodedAddress = encodeURIComponent(address);
        window.open(`https://www.google.com/maps/dir/?api=1&destination=${encodedAddress}`, '_blank');
    });
});