# ML Predictor Improvement Plan

## Overview
The current MLB predictor system has low accuracy (~53%) due to limited data, poor features, and lack of a proper machine learning framework. This plan outlines improvements to achieve >65% accuracy.

## Current Limitations

1. **Data Volume**: Only 207 predictions in history.json, insufficient for ML training
2. **Feature Set**: Basic statistics only (ERA, win pct, record) - missing critical predictors
3. **Model Architecture**: Custom Elo-based system instead of established ML algorithms
4. **Validation**: No proper train/test split to measure real performance
5. **Feature Engineering**: Missing advanced statistics like pitcher performance trends, park effects, bullpen strength

## Implementation Phases

### Phase 1: Data Engineering (Week 1-2)

#### 1.1 Expand Historical Data
- **Load**: Convert current predictions to training dataset
- **Split**: Create train/test split (70% train, 30% test)
- **Version**: Maintain version control for reproducible training

```python
# Example dataset creation
def create_training_dataset(history_predictions):
    features = []
    targets = []
    
    for pred in history_predictions:
        # Convert predictions to feature-target pairs
        feature_vector = {
            'home_era': pred.get('home_pitcher_era'),
            'away_era': pred.get('away_pitcher_era'),
            'home_win_pct': pred.get('home_record'),
            'away_win_pct': pred.get('away_record'),
            'home_home_wp': pred.get('home_wp_extra'),
            'away_bullpen_adj': pred.get('away_bullpen_adj'),
            'home_bullpen_adj': pred.get('home_bullpen_adj'),
            'park_factor': park_factors.get(pred['home_abbr'], 1.0),
            'rest_days_diff': calculate_rest_days_diff(...),
            'recent_performance': calculate_recent_trends(...),
            'EV': pred.get('ev'),  # Expected Value as target
            'won': pred.get('actual_winner') == pred.get('predicted_winner')
        }
        
        # Feature engineering (normalize, handle missing values)
        processed_features = process_features(feature_vector)
        features.append(processed_features)
        targets.append(pred.get('pick_result') == True)
    
    return np.array(features), np.array(targets)
```

#### 1.2 Feature Expansion
Add comprehensive feature set:

**Pitching Performance**
- Pitcher ERA, WHIP, K/9, BB/9
- Home/away splits for pitchers
- Recent 10-game performance trends

**Team Performance**
- Home road record splits
- Run differential (pointsFor/pointsAgainst)
- Strength of schedule metrics

**Situational Factors**
- Park effects (backfilled for missing data)
- Bullpen strength ratings
- Rest day advantages
- Travel fatigue factors

**Market Efficiency**
- Betting market efficiency metrics
- Line movement analysis
- Public money sentiment (if available)

#### 1.3 Data Quality Improvements
- Validate and clean existing data
- Handle missing values (imputation strategies)
- Detect and remove outliers
- Ensure consistent date formats and team abbreviations

### Phase 2: ML Framework Implementation (Week 3-4)

#### 2.1 Model Selection
Consider multiple approaches:

**Tabular Data Models**
- **XGBoost/LightGBM**: Proven performance for structured data
- **Random Forest**: Interpretable, handles non-linear relationships
- **Gradient Boosting**: Strong performance with imbalanced datasets

**Neural Network Approach**
- **TabNet/ML-PSM**: For structured tabular data
- **Transformer-based**: For relationship modeling

#### 2.2 Training Pipeline
```python
class MLBModelTrainer:
    def __init__(self):
        self.model = XGBClassifier(
            n_estimators=1000,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.8,
            colsample_bytree=0.8,
            gamma=0.1,
            reg_lambda=1.0,
            random_state=42
        )
        
    def train_model(self, X_train, y_train, X_val, y_val):
        # Train with validation monitoring
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            early_stopping_rounds=50,
            verbose=False
        )
        
        return self.model
        
    def evaluate_model(self, model, X_test, y_test):
        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]
        
        # Multiple evaluation metrics
        accuracy = accuracy_score(y_test, y_pred)
        auc_roc = roc_auc_score(y_test, y_proba)
        precision_recall = precision_score(y_test, y_pred)
        f1_score = f1_score(y_test, y_pred)
        
        return {
            'accuracy': accuracy,
            'auc_roc': auc_roc,
            'precision': precision,
            'f1_score': f1_score,
            'confusion_matrix': confusion_matrix(y_test, y_pred)
        }
```

#### 2.3 Model Persistence
Save trained models for production deployment:
```python
import pickle
import os

def save_model(model, file_path):
    with open(file_path, 'wb') as f:
        pickle.dump(model, f)
        
# Create version directory with timestamp
import datetime
version_dir = f"models/mlb_model_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
os.makedirs(version_dir, exist_ok=True)

save_model(trained_model, f"{version_dir}/model.pkl")
save_model(feature_processor, f"{version_dir}/feature_processor.pkl")
```

### Phase 3: System Integration (Week 5-6)

#### 3.1 Real-time Prediction Pipeline
```python
def predict_current_games(pipeline, features):
    """Generate predictions for current day games"""
    # Load model and feature processor
    model = load_model('models/latest/model.pkl')
    feature_processor = load_model('models/latest/feature_processor.pkl')
    
    # Process current games data
    processed_features = feature_processor.transform(current_game_features)
    
    # Generate predictions
    predictions = model.predict(processed_features)
    probabilities = model.predict_proba(processed_features)[:, 1]
    
    # Format for display
    return format_predictions(predictions, probabilities)
```

#### 3.2 API Integration
- Create REST API endpoint for predictions
- Add caching layer for performance
- Implement monitoring and alerting
- Set up model versioning

#### 3.3 Evaluation Dashboard
- Display model performance metrics
- Show feature importance analysis
- Track prediction confidence intervals
- Monitor data drift

### Phase 4: Testing & Validation (Week 7-8)

#### 4.1 Cross-Validation
- Implement k-fold cross-validation
- Test on different time windows
- Validate on out-of-sample data

#### 4.2 Performance Metrics
Track and optimize:

**Classification Metrics**
- Accuracy: Target >65%
- Precision-Recall trade-offs
- AUC-ROC for probabilistic predictions

**Business Metrics**
- Value over benchmark (betting ROI)
- Risk-adjusted returns
- Predictive confidence calibration

#### 4.3 A/B Testing
- Compare ML model vs current Elo system
- Measure impact on user engagement
- Monitor betting performance

### Phase 5: Maintenance & Monitoring (Ongoing)

#### 5.1 Automated Retraining
- Schedule weekly retraining with new data
- Implement performance monitoring
- Set up alerting for model degradation

#### 5.2 Data Quality Checks
- Monitor feature distributions
- Detect data drift
- Ensure data quality standards

#### 5.3 Performance Optimization
- Optimize model for inference speed
- Cache predictions for frequent requests
- Scale infrastructure as needed

## Expected Outcomes

### Short-term (Week 1-4)
- Improved accuracy from ~53% to ~60%
- Better handling of edge cases
- More interpretable results
- Reduced prediction variance

### Medium-term (Week 5-8)
- Achieved 65%+ accuracy on holdout data
- Reliable production deployment
- Automated retraining pipeline
- Monitoring and alerting system

### Long-term (Month 2+)
- Consistent >70% accuracy
- Advanced features implemented
- Full ML lifecycle management
- Competitive advantage in predictions

## Implementation Timeline

| Week | Milestones |
|------|-----------|
| 1-2 | Data collection, feature engineering |
| 3-4 | ML framework selection and training |
| 5-6 | System integration and API setup |
| 7-8 | Testing, validation, and deployment |
| 9-10 | Monitoring, maintenance, and continuous improvement |

## Required Resources

### Technical
- **Hardware**: 4+ CPU cores, 16GB+ RAM for training
- **Software**: Python ecosystem (scikit-learn, XGBoost, pandas, etc.)
- **Infrastructure**: Model training environment, versioning system

### Human
- **Data Scientist**: 1-2 researchers for feature engineering
- **ML Engineer**: 1 engineer for pipeline development
- **DevOps**: 1 engineer for deployment and monitoring

## Risk Mitigation

### Data Risks
- **Solution**: Implement backup data sources, automated data validation
- **Contingency**: Fallback to current Elo system if ML fails

### Technical Risks
- **Solution**: Gradual rollout with A/B testing, rollback capabilities
- **Contingency**: Manual override for critical predictions

### Operational Risks
- **Solution**: Comprehensive logging, monitoring, and automated recovery
- **Contingency**: Secondary prediction system as backup

## Conclusion

This comprehensive plan transitions the current heuristic-based predictor to a robust, data-driven ML system that can achieve 65%+ accuracy. The phased approach ensures manageable implementation while delivering significant performance improvements.

The key to success lies in:
1. **Quality data**: Rich historical dataset with comprehensive features
2. **Proper ML framework**: Leveraging proven algorithms and methodologies
3. **Rigorous validation**: Ensuring generalization to new, unseen data
4. **Sustainable operations**: Automated pipelines and monitoring

By following this plan, the MLB predictor will transition from a basic statistical model to a sophisticated machine learning system capable of competitive performance.
