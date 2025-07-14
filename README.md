# Bot Club - Algorithmic Trading Platform

A full-stack algorithmic trading platform built with the FARM stack (FastAPI, React, MongoDB, Docker) that enables users to create, backtest, and manage trading strategies with real-time market data integration. The platform features a microservices architecture with separate backend services for enhanced backtesting and trading operations.

## 🚀 Features

### Authentication & User Management
- Secure JWT-based authentication
- User registration and login
- Protected routes and role-based access
- Profile management with personal information and preferences

### Trading Strategy Development
- Interactive strategy builder with visual components
- Real-time strategy backtesting engine
- Strategy performance analytics and metrics
- Save and manage multiple trading strategies
- Strategy sharing and collaboration (planned)

### Market Data Integration
- Real-time market data feeds via Alpaca API, Polygon API or Yahoo Finance API.
- Historical price data analysis
- Multiple asset class support (stocks, crypto, forex)
- Technical indicator calculations using Polars TA

### Portfolio Management
- Real-time portfolio tracking
- Performance metrics and analytics
- Trade history and reporting
- Risk management tools

### Enhanced Backtesting
- Multi-timeframe backtesting capabilities
- Advanced technical indicators
- Real-time backtest monitoring
- Comprehensive performance metrics

## 🏗️ Project Structure

```
bot-club/
├── backend/                 # FastAPI backend application
│   ├── src/
│   │   ├── main.py         # FastAPI application entry point
│   │   ├── models/         # Pydantic models and schemas
│   │   │   ├── user.py     # User models (UserCreate, UserInDB, UserProfile)
│   │   │   ├── strategy.py # Strategy models and schemas
│   │   │   └── trading.py  # Trading and portfolio models
│   │   ├── routes/         # API route handlers
│   │   │   ├── auth.py     # Authentication endpoints
│   │   │   ├── users.py    # User profile management
│   │   │   ├── strategies.py # Strategy CRUD operations
│   │   │   ├── trading.py  # Trading operations
│   │   │   └── market.py   # Market data endpoints
│   │   ├── crud/           # Database operations
│   │   │   ├── user.py     # User database operations
│   │   │   └── strategy.py # Strategy database operations
│   │   ├── services/       # Business logic services
│   │   │   ├── backtest.py # Backtesting engine
│   │   │   └── market_data.py # Market data service
│   │   ├── utils/          # Utility functions
│   │   │   └── security.py # JWT and password hashing
│   │   ├── database/       # Database configuration
│   │   │   └── client.py   # MongoDB connection
│   │   └── dependencies.py # FastAPI dependencies
│   ├── .env               # Environment variables
│   ├── requirements.txt   # Python dependencies
│   └── Dockerfile         # Backend container configuration
├── frontend/              # React frontend application
│   ├── src/
│   │   ├── components/    # React components
│   │   │   ├── common/    # Shared components (Sidebar, Navbar)
│   │   │   ├── auth/      # Authentication components
│   │   │   ├── account/   # User profile components
│   │   │   ├── strategies/ # Strategy builder components
│   │   │   ├── trading/   # Trading dashboard components
│   │   │   └── router/    # Routing and protection
│   │   ├── api/           # API client and services
│   │   │   ├── Client.js  # Main API client with authentication
│   │   │   └── AlpacaService.js # Trading service integration
│   │   ├── contexts/      # React contexts
│   │   │   ├── AuthContext.js # Authentication state
│   │   │   ├── StrategyContext.js # Strategy state
│   │   │   └── AlpacaContext.js # Trading state
│   │   └── App.js         # Main React application
│   ├── package.json       # Node.js dependencies
│   └── Dockerfile         # Frontend container configuration
├── docker-compose.yml     # Multi-container orchestration
└── README.md             # Project documentation
```

## 🛠️ Technology Stack

### Backend
- **FastAPI**: Modern Python web framework with automatic API documentation
- **MongoDB**: NoSQL database for flexible data storage
- **PyMongo**: MongoDB driver for Python
- **JWT**: JSON Web Tokens for secure authentication
- **Pydantic**: Data validation and serialization
- **CORS**: Cross-origin resource sharing support

### Frontend
- **React 18**: Modern JavaScript library for building user interfaces
- **Material-UI (MUI)**: React component library with Google's Material Design
- **React Router**: Declarative routing for React applications
- **Context API**: State management for authentication and app state
- **Fetch API**: HTTP client for API communication

### Database
- **MongoDB**: Document-based NoSQL database
- **Collections**: `user`, `strategy`, `trade`, `backtest`, `user_config`
- **Indexes**: Optimized queries for user data and strategy lookups

## 🚀 Getting Started

### Prerequisites

- **Node.js** (v16 or higher)
- **Python** (3.9 or higher)
- **MongoDB** (local installation or MongoDB Atlas)
- **Docker & Docker Compose** (optional, for containerized deployment)

### Environment Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd bot-club
   ```

2. **Backend Setup:**
   ```bash
   cd backend
   
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   
   # Create .env file
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Frontend Setup:**
   ```bash
   cd frontend
   
   # Install dependencies
   npm install
   
   # Create environment file
   cp .env.example .env.local
   # Edit .env.local with your configuration
   ```

### Configuration

#### Backend Environment Variables (`.env`)
```env
# JWT Configuration
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this-in-production

# MongoDB Configuration
LOCAL_DB=true
MONGO_URL=mongodb://localhost:27017/bot_club_db
MONGO_DB_NAME=bot_club_db

# For production with MongoDB Atlas
MONGO_CONNECTION_STRING=mongodb+srv://username:password@cluster.mongodb.net/
MONGO_USERNAME=your-username
MONGO_PASSWORD=your-password

# Environment
ENVIRONMENT=development
```

#### Frontend Environment Variables (`.env.local`)
```env
REACT_APP_API_BASE_URL=http://localhost:8000
REACT_APP_ENVIRONMENT=development
```

### Running the Application

#### Option 1: Local Development

1. **Start MongoDB:**
   ```bash
   # If using local MongoDB
   mongod
   
   # Or start MongoDB service
   brew services start mongodb/brew/mongodb-community  # macOS
   sudo systemctl start mongod  # Linux
   ```

2. **Start the Backend:**
   ```bash
   cd backend
   source venv/bin/activate
   uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Start the Frontend:**
   ```bash
   cd frontend
   npm start
   ```

4. **Access the Application:**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

#### Option 2: Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up --build

# Run in detached mode
docker-compose up -d --build
```

## 📚 API Documentation

### Authentication Endpoints
- `POST /api/auth/register` - User registration
- `POST /api/auth/token` - User login (OAuth2 compatible)

### User Management
- `GET /api/users/me` - Get current user profile
- `PUT /api/users/me` - Update user profile

### Strategy Management
- `GET /api/strategies/` - List user strategies
- `POST /api/strategies/` - Create new strategy
- `GET /api/strategies/{id}` - Get strategy details
- `PUT /api/strategies/{id}` - Update strategy
- `DELETE /api/strategies/{id}` - Delete strategy
- `POST /api/strategies/{id}/backtest` - Run strategy backtest

### Trading Operations
- `GET /api/trading/portfolio` - Get portfolio overview
- `GET /api/trading/positions` - Get active positions
- `GET /api/trading/history` - Get trading history

### Market Data
- `GET /api/market/data` - Get market data for symbols
- `GET /api/market/symbols` - Get available trading symbols

## 🏃‍♂️ Development Workflow

### Adding New Features

1. **Backend Development:**
   - Add models in `backend/src/models/`
   - Create CRUD operations in `backend/src/crud/`
   - Implement API routes in `backend/src/routes/`
   - Add business logic in `backend/src/services/`

2. **Frontend Development:**
   - Create components in `frontend/src/components/`
   - Add API calls in `frontend/src/api/`
   - Implement state management with Context API
   - Add routing in `frontend/src/router/`

### Testing

```bash
# Backend testing
cd backend
python -m pytest

# Frontend testing
cd frontend
npm test
```

### Code Quality

```bash
# Backend formatting
black backend/src/
flake8 backend/src/

# Frontend formatting
cd frontend
npm run format
npm run lint
```

## 🔒 Security Features

- **JWT Authentication**: Secure token-based authentication
- **Password Hashing**: PBKDF2 with SHA-256 for password security
- **CORS Protection**: Configured cross-origin resource sharing
- **Input Validation**: Pydantic models for request validation
- **Protected Routes**: Frontend route protection based on authentication
- **Environment Variables**: Sensitive data stored in environment files

## 📊 Database Schema

### Users Collection
```javascript
{
  _id: ObjectId,
  userName: String,
  email: String,
  firstName: String,
  lastName: String,
  hashed_password: String,
  phone: String,
  address: {
    addressLine1: String,
    addressLine2: String,
    city: String,
    state: String,
    zipCode: String
  },
  timezone: String,
  bio: String,
  profileImage: String,
  role: String,
  isActive: Boolean,
  createdAt: Date
}
```

### Strategies Collection
```javascript
{
  _id: ObjectId,
  userId: ObjectId,
  name: String,
  description: String,
  strategyType: String,
  parameters: Object,
  status: String,
  createdAt: Date,
  updatedAt: Date,
  backtestResults: Array
}
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:
- Create an issue in the GitHub repository
- Check the API documentation at `/docs` endpoint
- Review the frontend console for debugging information

## 🗺️ Roadmap

- [ ] Advanced backtesting with multiple timeframes
- [ ] Real-time trading execution
- [ ] Strategy marketplace and sharing
- [ ] Advanced risk management tools
- [ ] Mobile application
- [ ] Integration with multiple brokers
- [ ] Machine learning strategy optimization
- [ ] Social trading features