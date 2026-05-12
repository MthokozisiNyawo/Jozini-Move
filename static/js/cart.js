// Cart functionality for Jozini Move

$(document).ready(function() {
    // Add to cart
    $('.add-to-cart').click(function() {
        const itemId = $(this).data('item-id');
        const shopId = $(this).data('shop-id');
        
        // Show quantity modal
        $('#quantityModal').modal('show');
        $('#confirmAddToCart').off('click').on('click', function() {
            const quantity = $('#itemQuantity').val();
            
            $.ajax({
                url: '/shop/add-to-cart',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    item_id: itemId,
                    quantity: quantity
                }),
                success: function(response) {
                    if (response.success) {
                        toastr.success(response.message);
                        updateCartCount(shopId, response.cart_count);
                        $('#quantityModal').modal('hide');
                    } else {
                        toastr.error(response.message);
                    }
                },
                error: function() {
                    toastr.error('Failed to add item to cart');
                }
            });
        });
    });
    
    // Update cart item quantity
    $('.update-cart').click(function() {
        const cartId = $(this).data('cart-id');
        const action = $(this).data('action');
        
        $.ajax({
            url: '/shop/update-cart',
            method: 'POST',
            data: {
                cart_id: cartId,
                action: action
            },
            success: function(response) {
                if (response.success) {
                    if (action === 'remove') {
                        $(`#cart-item-${cartId}`).fadeOut(300, function() {
                            $(this).remove();
                            updateCartTotals();
                        });
                    } else {
                        location.reload();
                    }
                    updateCartTotals();
                } else {
                    toastr.error(response.message);
                }
            },
            error: function() {
                toastr.error('Failed to update cart');
            }
        });
    });
    
    // Update cart totals
    function updateCartTotals() {
        let subtotal = 0;
        $('.item-total').each(function() {
            subtotal += parseFloat($(this).text().replace('R', '').replace(',', ''));
        });
        
        const deliveryFee = parseFloat($('#deliveryFee').data('fee') || 20);
        const serviceFee = 5;
        const total = subtotal + deliveryFee + serviceFee;
        
        $('.subtotal').text(formatCurrency(subtotal));
        $('.total').text(formatCurrency(total));
    }
    
    // Bulk add to cart from menu grid
    $('.quick-add').click(function() {
        const itemId = $(this).data('item-id');
        const price = $(this).data('price');
        
        // Add directly without modal
        $.ajax({
            url: '/shop/add-to-cart',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                item_id: itemId,
                quantity: 1
            }),
            success: function(response) {
                if (response.success) {
                    toastr.success('Item added to cart');
                    const badge = $(`.cart-badge`);
                    if (badge.length) {
                        badge.text(response.cart_count).show();
                    }
                } else {
                    toastr.error(response.message);
                }
            }
        });
    });
    
    // Clear entire cart
    $('#clearCart').click(function() {
        if (confirm('Are you sure you want to clear your entire cart?')) {
            $.ajax({
                url: '/shop/clear-cart',
                method: 'POST',
                success: function(response) {
                    if (response.success) {
                        location.reload();
                    }
                }
            });
        }
    });
    
    // Save cart for later
    $('.save-for-later').click(function() {
        const cartId = $(this).data('cart-id');
        $.ajax({
            url: '/shop/save-for-later',
            method: 'POST',
            data: { cart_id: cartId },
            success: function(response) {
                if (response.success) {
                    toastr.success('Item saved for later');
                    location.reload();
                }
            }
        });
    });
});