# Jozini Move - Local Delivery Platform

![Jozini Move Banner](app/static/img/hero-delivery.svg)

Jozini Move is a comprehensive local delivery platform connecting customers, local shops, and delivery drivers in Jozini and surrounding areas. The platform enables users to order food and items from local shops, track deliveries in real-time, and provides earning opportunities for drivers.

## 🚀 Features

### For Customers
- 🛍️ Browse local shops and menus
- 🔍 Search and filter by category
- 🛒 Add items to cart and checkout
- 💳 Multiple payment options (Cash, Card, Mobile Money)
- 📍 Real-time order tracking
- ⭐ Rate and review orders
- 📱 Mobile-responsive design
- 🔔 Push notifications

### For Shop Owners
- 📝 Register and manage your shop
- 📋 Add/edit menu items with images
- 📊 View order statistics and analytics
- ✅ Update order status (confirm, prepare, ready)
- 📈 Track revenue and performance
- 🏷️ Manage categories and pricing
- 📸 Upload shop logo and item images

### For Drivers
- 🚚 View available delivery orders
- ✅ Accept and manage deliveries
- 📍 Navigation assistance
- 💰 Track earnings in real-time
- ⭐ Customer ratings
- 📊 Delivery statistics and performance metrics
- 🔐 Secure delivery PIN verification

### For Administrators
- 👥 User management (customers, drivers, shop owners)
- 🏪 Shop approval and moderation
- 📦 Order monitoring and management
- 💵 Platform revenue tracking
- 📊 Advanced analytics and reports
- 🗺️ Delivery zone configuration
- ⚙️ System settings management
- 📝 Audit logs for security

## 🛠️ Technology Stack

### Backend
- **Python 3.9+** - Core programming language
- **Flask 2.0.3** - Web framework
- **SQLAlchemy** - ORM for database operations
- **Flask-Login** - Authentication and session management
- **Flask-Migrate** - Database migrations
- **Celery** - Background task processing
- **Redis** - Caching and message broker

### Database
- **PostgreSQL** - Production database
- **SQLite** - Development database

### Frontend
- **Bootstrap 5** - Responsive UI framework
- **jQuery** - DOM manipulation and AJAX
- **Chart.js** - Data visualization
- **Font Awesome 6** - Icons
- **AOS** - Scroll animations

### Third-Party Integrations
- **SendGrid** - Email notifications
- **Africa's Talking** - SMS notifications
- **PayFast** - Payment processing (South Africa)
- **Sentry** - Error tracking and monitoring
- **Google Maps** - Location services

## 📋 Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- Virtual environment (recommended)
- PostgreSQL (for production) or SQLite (for development)
- Redis (for caching and background tasks)

## 🔧 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/MthokozisiNyawo/jozini-move.git
cd jozini-move