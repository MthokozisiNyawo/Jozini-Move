// Admin dashboard JavaScript

$(document).ready(function() {
    // Toggle user status
    $('.toggle-user-status').click(function() {
        const userId = $(this).data('user-id');
        const btn = $(this);
        
        if (confirm('Are you sure you want to change this user\'s status?')) {
            $.ajax({
                url: `/admin/users/${userId}/toggle-status`,
                method: 'POST',
                success: function(response) {
                    if (response.success) {
                        toastr.success(response.message);
                        location.reload();
                    } else {
                        toastr.error(response.message);
                    }
                }
            });
        }
    });
    
    // Approve shop
    $('.approve-shop').click(function() {
        const shopId = $(this).data('shop-id');
        
        if (confirm('Approve this shop? It will become visible to customers.')) {
            $.ajax({
                url: `/admin/shops/${shopId}/approve`,
                method: 'POST',
                success: function(response) {
                    if (response.success) {
                        toastr.success(response.message);
                        location.reload();
                    } else {
                        toastr.error(response.message);
                    }
                }
            });
        }
    });
    
    // Suspend shop
    $('.suspend-shop').click(function() {
        const shopId = $(this).data('shop-id');
        
        if (confirm('Suspend this shop? It will no longer accept orders.')) {
            $.ajax({
                url: `/admin/shops/${shopId}/suspend`,
                method: 'POST',
                success: function(response) {
                    if (response.success) {
                        toastr.success(response.message);
                        location.reload();
                    } else {
                        toastr.error(response.message);
                    }
                }
            });
        }
    });
    
    // Delete delivery zone
    $('.delete-zone').click(function() {
        const zoneId = $(this).data('zone-id');
        
        if (confirm('Delete this delivery zone? This action cannot be undone.')) {
            $.ajax({
                url: `/admin/delivery-zones/${zoneId}/delete`,
                method: 'POST',
                success: function(response) {
                    if (response.success) {
                        toastr.success('Zone deleted successfully');
                        location.reload();
                    } else {
                        toastr.error('Failed to delete zone');
                    }
                }
            });
        }
    });
    
    // Clear cache
    $('#clearCacheBtn').click(function() {
        if (confirm('Clear application cache? This may temporarily slow down the site.')) {
            $.ajax({
                url: '/admin/clear-cache',
                method: 'POST',
                success: function(response) {
                    if (response.success) {
                        toastr.success('Cache cleared successfully');
                    } else {
                        toastr.error('Failed to clear cache');
                    }
                }
            });
        }
    });
    
    // Export report
    $('.export-report').click(function() {
        const reportType = $(this).data('report');
        const format = $(this).data('format');
        const startDate = $('#start_date').val();
        const endDate = $('#end_date').val();
        
        window.location.href = `/admin/reports/export?type=${reportType}&format=${format}&start_date=${startDate}&end_date=${endDate}`;
    });
    
    // Real-time dashboard refresh
    let statsInterval = null;
    
    if ($('#admin-dashboard').length) {
        statsInterval = setInterval(function() {
            $.ajax({
                url: '/admin/api/stats',
                method: 'GET',
                success: function(data) {
                    $('#online-users').text(data.online_users || 0);
                    $('#active-drivers').text(data.active_drivers || 0);
                    $('#pending-orders-count').text(data.pending_orders || 0);
                    $('#today-revenue').text(formatCurrency(data.today_revenue || 0));
                }
            });
        }, 30000);
    }
    
    // Cleanup on page unload
    $(window).on('beforeunload', function() {
        if (statsInterval) {
            clearInterval(statsInterval);
        }
    });
    
    // Bulk actions
    $('#bulkActionBtn').click(function() {
        const action = $('#bulkAction').val();
        const selectedIds = [];
        
        $('.select-item:checked').each(function() {
            selectedIds.push($(this).val());
        });
        
        if (selectedIds.length === 0) {
            toastr.warning('Please select at least one item');
            return;
        }
        
        if (confirm(`Are you sure you want to ${action} ${selectedIds.length} item(s)?`)) {
            $.ajax({
                url: '/admin/bulk-action',
                method: 'POST',
                data: {
                    action: action,
                    ids: selectedIds.join(',')
                },
                success: function(response) {
                    if (response.success) {
                        toastr.success(response.message);
                        location.reload();
                    } else {
                        toastr.error(response.message);
                    }
                }
            });
        }
    });
    
    // Select all checkbox
    $('#selectAll').change(function() {
        $('.select-item').prop('checked', $(this).prop('checked'));
    });
    
    // Date range picker initialization
    if ($('#dateRange').length) {
        // Initialize date range picker (would need plugin)
        console.log('Date range picker initialized');
    }
    
    // Settings form validation
    $('#settingsForm').submit(function(e) {
        const deliveryFee = $('#delivery_fee').val();
        const serviceFee = $('#service_fee').val();
        
        if (parseFloat(deliveryFee) < 0) {
            toastr.error('Delivery fee cannot be negative');
            e.preventDefault();
        }
        
        if (parseFloat(serviceFee) < 0) {
            toastr.error('Service fee cannot be negative');
            e.preventDefault();
        }
    });
});