# 🏀 NBA StatLab

> Advanced predictive analytics system for NBA games using dynamic Elo rating and statistical modeling

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Data Science](https://img.shields.io/badge/Data-Science-orange.svg)](https://github.com/rczap1/NBA-StatLab.git)

---

## 📊 Project Overview

A personal data science project focused on predicting NBA game outcomes using statistical modeling and machine learning techniques. The system combines traditional Elo rating methodology with modern data analysis approaches to achieve high prediction accuracy.

### 💡 Project Motivation
A personal project exploring the intersection of sports analytics and data science:
- **Statistical Modeling** - Elo rating systems with dynamic parameters
- **Machine Learning** - Predictive analytics and model evaluation
- **Data Engineering** - Real-time data processing and API integration
- **Performance Analysis** - Brier score, accuracy metrics, and validation

### 🎯 Model Performance
- **Prediction Accuracy**: ~67% on historical data
- **Brier Score**: 0.20-0.22 (lower is better)
- **Sample Size**: 1000+ games analyzed
- **Validation**: Out-of-sample testing with rolling windows

---

## ✨ Key Features

### 🔮 Predictive Modeling
- **Dynamic Elo Rating System**
  - Adaptive K-factor based on season phase
  - Margin of Victory (MOV) adjustment
  - Home court advantage modeling (+60 points)
  - Between-season regression to mean

- **Contextual Factors**
  - Back-to-back game detection and impact
  - Rest advantage calculation (3+ days)
  - Travel fatigue considerations
  - Schedule strength analysis

- **Injury Impact Analysis**
  - Automatic player tier classification (5 levels)
  - Dynamic impact calculation based on player value
  - Real-time injury data integration via ESPN API

### 📊 Analytics & Reporting
- Real-time Elo rankings for all 30 NBA teams
- Top 50 player rankings by calculated impact
- Detailed team statistics and comparisons
- Historical accuracy tracking and validation
- Season-over-season performance analysis

### 💻 Technical Implementation
- **CLI Interface** with Rich library for enhanced UX
- **Web Dashboard** using Streamlit (optional)
- **Modular Architecture** for easy extension
- **Automated Data Pipeline** with caching and rate limiting
- **Comprehensive Testing** and validation framework

---

## 🚀 Quick Start

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/rczap1/NBA-StatLab.git
cd NBA-StatLab

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the system
python app.py menu
```

### Basic Usage

```bash
# Interactive menu
python app.py menu

# Generate predictions for today
python app.py predictions

# View Elo rankings
python app.py rankings

# Update historical Elo ratings
python app.py update-elo --start 2024-10-01 --end 2024-11-30


---

## 📁 Project Structure

```
nba-prediction-system/
├── app.py                    # Main CLI application
├── requirements.txt         # Python dependencies
│
├── services/               # Core modules
│   ├── predictions.py     # Elo system & predictions
│   ├── calendar.py        # Game schedule management
│   ├── injuries.py        # Injury tracking system
│   ├── player_tiers.py    # Player classification
│   ├── game_analysis.py   # Comprehensive game analysis
│   ├── team_stats.py      # Team statistics
│   └── stats.py           # Player statistics
│
└── data/                   # Persistent data
    ├── elo_ratings.json
    ├── schedule_cache.json
    └── tiers/              # Player tiers by season
```

---

## 🎮 Features Overview

### 1. 🎯 Game Predictions
- View daily NBA schedule
- Generate predictions with confidence levels
- Comprehensive game-by-game analysis
- Injury impact reports
- Historical accuracy evaluation

### 2. 📊 Statistical Analysis
- Live Elo rankings (all 30 teams)
- Top 50 players by impact
- Player tier distribution
- Detailed team statistics
- Season-over-season comparisons

### 3. ⚙️ System Management
- Historical Elo calculation
- Player tier updates
- Data validation tools
- Performance monitoring

---

## 🧮 Methodology

### Elo Rating System

**Core Formula:**
```
Expected Win% = 1 / (1 + 10^(-diff/400))
New Rating = Old Rating + K × (Result - Expected)
```

**Dynamic K-factor:**
- October-December: K=30 (early season volatility)
- January-March: K=20 (mid season)
- April-June: K=15 (playoffs stability)

**Margin of Victory Multiplier:**
```
MOV = log(|point_diff| + 1) × (2.2 / (elo_diff × 0.001 + 2.2))
```

This approach accounts for the magnitude of victory while preventing excessive rating changes from blowouts.

### Injury Impact Model

**5-Tier Player Classification:**
- **SUPERSTAR** (Top 15): -60 Elo impact
- **STAR** (16-40): -40 Elo impact
- **STARTER** (41-100): -25 Elo impact
- **ROTATION** (101-200): -12 Elo impact
- **BENCH** (Remaining): -5 Elo impact

**Automatic Calculation Based On:**
- Points Per Game (30% weight)
- Efficiency Rating (25% weight)
- Plus/Minus Impact (20% weight)
- Advanced Metrics (15% weight)
- All-Around Statistics (10% weight)

### Model Validation

**Metrics Used:**
- **Accuracy**: Percentage of correct predictions
- **Brier Score**: Measures probability calibration
- **Log Loss**: Penalizes confident wrong predictions
- **Confusion Matrix**: Detailed performance breakdown

**Validation Strategy:**
- Out-of-sample testing on future games
- Rolling window validation
- Cross-season consistency checks
- Sensitivity analysis on key parameters

---

## 📈 Example Output

### Daily Predictions

```
🔮 NBA Predictions — 2025-12-08

Game                Predicted  Probability  Confidence
──────────────────────────────────────────────────────
BOS vs LAL         BOS        72.3%        🔥 High
GSW vs PHX         PHX        61.5%        ✓ Medium
DEN vs MIA         DEN        58.2%        ✓ Medium
...

📊 8 games | 3 high confidence | 4 with injury impact
```

### Elo Rankings

```
🏆 NBA Elo Rankings

Rank  Team  Rating   vs Mean  Tier
───────────────────────────────────
1     OKC   1795.6   +295.6   Elite 🌟
2     DEN   1721.4   +221.4   Elite 🌟
3     SAS   1710.5   +210.5   Elite 🌟
...
```

---

## 🔧 Technical Details

### Data Sources

1. **nba_api** (Official NBA Statistics)
   - Game results and schedules
   - Player and team statistics
   - No API key required
   - Built-in rate limiting

2. **ESPN API** (Injury Reports)
   - Real-time injury data
   - Player status updates
   - Free public API

### Performance Optimizations

- **Caching Strategy**: 1-hour TTL for API responses
- **Rate Limiting**: 600ms between API calls
- **Incremental Updates**: Only process new games
- **Checkpoint System**: Resume from last processed date

### Configuration

Key parameters in `services/predictions.py`:

```python
# Adjustable parameters
HOME_COURT_BONUS = 60.0        # Home advantage
BACK_TO_BACK_PENALTY = -50.0   # B2B fatigue
REST_ADVANTAGE = 25.0           # 3+ days rest

# K-factors by season phase
K_EARLY_SEASON = 30.0   # Oct-Dec
K_MID_SEASON = 20.0     # Jan-Mar
K_LATE_SEASON = 15.0    # Apr-Jun
```

### 🤖 AI-Assisted Development

This project leveraged AI assistance throughout the development process to enhance productivity and code quality. AI tools were used for:

- **Code Architecture & Design**: Structuring modular services and establishing design patterns
- **Algorithm Implementation**: Refining the Elo rating system and statistical calculations
- **Code Optimization**: Improving performance through efficient data processing and caching strategies
- **Documentation**: Generating comprehensive docstrings and technical explanations
- **Debugging & Problem-Solving**: Identifying and resolving complex issues in API integration and data processing
- **Best Practices**: Ensuring adherence to Python conventions and modern software engineering principles

While AI provided valuable guidance and accelerated development, all strategic decisions, domain expertise, and final implementations were human-driven. The AI served as an intelligent coding assistant, enabling faster iteration and higher quality output.

---

## 📚 Project Applications

### Learning Objectives
1. Can Elo ratings effectively predict NBA game outcomes?
2. How do contextual factors (rest, injuries) affect predictions?
3. What is the optimal K-factor strategy for NBA?
4. How does prediction accuracy vary across the season?

### Potential Extensions
- Integration with advanced machine learning models
- Player-level prediction granularity
- Real-time model updating during games
- Alternative rating systems comparison (Glicko-2, TrueSkill)
- Ensemble methods combining multiple approaches

### Skills Demonstrated
- Practical application of statistical methods
- Real-world data engineering challenges
- Model evaluation and validation techniques
- Software engineering best practices
- API integration and data processing

---

## 🤝 Contributing

This is a personal project, but contributions and suggestions are welcome! Areas for collaboration:

- **Statistical Methods**: Alternative rating systems, ensemble models
- **Feature Engineering**: New predictive factors
- **Validation**: More robust testing frameworks
- **Visualization**: Enhanced data presentation
- **Documentation**: Improved explanations and tutorials

---

## 📝 Future Development

### Planned Enhancements
- [ ] Machine learning ensemble (Elo + ML models)
- [ ] Player-level prop predictions
- [ ] Live game probability updates
- [ ] Enhanced visualization dashboard
- [ ] Comprehensive backtesting framework
- [ ] Comparative analysis with other systems

### Research Directions
- [ ] Alternative rating systems comparison
- [ ] Feature importance analysis
- [ ] Optimal parameter search via grid search
- [ ] Uncertainty quantification
- [ ] Causal inference for injury impact
- [ ] Integration with other sports prediction models

---

## 📖 Documentation

### Key Concepts

**Elo Rating**: A method for calculating relative skill levels, originally designed for chess, adapted here for team sports.

**K-factor**: Controls how much ratings change after each game. Higher values = more volatile, lower values = more stable.

**Margin of Victory**: Accounts for the magnitude of wins, not just binary outcomes.

**Brier Score**: Measures the accuracy of probabilistic predictions. Score of 0 = perfect predictions, 0.25 = baseline (coin flip).

### References

1. Elo, A. (1978). *The Rating of Chessplayers, Past and Present*
2. FiveThirtyEight NBA Predictions Methodology
3. Glickman, M. (1999). "Parameter Estimation in Large Dynamic Paired Comparison Experiments"
4. Silver, N. (2012). *The Signal and the Noise*

---

## 🐛 Troubleshooting

### Common Issues

**Error: "Team abbreviation not found"**
- ESPN uses different abbreviations (e.g., "SA" vs "SAS")
- Fixed with automatic mapping in `services/calendar.py`

**Error: "Rate limit exceeded"**
- Built-in 600ms delay between API calls
- Increase delay in `services/stats.py` if needed

**Error: "Player tier not found"**
- Run: `python app.py menu` → System → Update Player Tiers

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👨‍💻 Author

**[Rodrigo Carvalho]** - BSc at Engineering and Management of Information Systems

**Contact:**
- Email: rodrigofcarvalho421@gmail.com
- LinkedIn: [linkedin.com/in/rodrigo-fernandes-carvalho](https://linkedin.com/in/rodrigo-fernandes-carvalho)
- GitHub: [rczap1](https://github.com/rczap1)

---

## 🙏 Acknowledgments

- **nba_api** - Official NBA statistics access
- **ESPN API** - Injury reports and schedules
- **FiveThirtyEight** - Elo methodology inspiration
- **Rich** - Modern CLI interface
- **Streamlit** - Interactive web framework

---

## 📊 Project Statistics

- **Lines of Code**: ~3,000+
- **Modules**: 10+ specialized services
- **Data Points**: 1,000+ games analyzed
- **Prediction Accuracy**: ~67%
- **Development Time**: 5 months

---

⭐ If you found this project interesting or useful, please consider giving it a star!

**Built with 📊 and ❤️ for sports analytics**
