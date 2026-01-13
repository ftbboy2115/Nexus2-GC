"""
Unit tests for CatalystClassifier - regex pattern matching for news catalysts.
"""

import pytest


class TestCatalystClassifierPatterns:
    """Test the expanded regex patterns in CatalystClassifier."""
    
    @pytest.fixture
    def classifier(self):
        from nexus2.domain.automation.catalyst_classifier import CatalystClassifier
        return CatalystClassifier()
    
    # --- Acquisition patterns ---
    def test_acquisition_acquires(self, classifier):
        """Test 'acquires' keyword."""
        result = classifier.classify("XTL Biopharmaceuticals Acquires 85% of NeuroNOS")
        assert result.is_positive is True
        assert result.catalyst_type == "acquisition"
    
    def test_acquisition_merger(self, classifier):
        """Test 'merger' keyword."""
        result = classifier.classify("Company announces merger with competitor")
        assert result.is_positive is True
        assert result.catalyst_type == "acquisition"
    
    def test_acquisition_takeover(self, classifier):
        """Test 'takeover' keyword."""
        result = classifier.classify("Hostile takeover bid announced at 40% premium")
        assert result.is_positive is True
        assert result.catalyst_type == "acquisition"
    
    # --- Clinical data patterns ---
    def test_fda_clinical_data(self, classifier):
        """Test 'clinical data' keyword."""
        result = classifier.classify("Company announces promising early clinical data")
        assert result.is_positive is True
        assert result.catalyst_type == "fda"
    
    def test_fda_clinical_results(self, classifier):
        """Test 'clinical results' keyword."""
        result = classifier.classify("Positive clinical results from Phase 2 trial")
        assert result.is_positive is True
        assert result.catalyst_type == "fda"
    
    def test_fda_complete_resolution(self, classifier):
        """Test 'complete resolution' keyword (BCTX case)."""
        result = classifier.classify("BriaCell Reports Sustained Complete Resolution of Lung Metastasis")
        assert result.is_positive is True
        assert result.catalyst_type == "fda"
    
    def test_fda_promising_clinical(self, classifier):
        """Test 'promising clinical' keyword (ERAS case)."""
        result = classifier.classify("Erasca Announces Promising Early Clinical Data for ERAS-0015")
        assert result.is_positive is True
        assert result.catalyst_type == "fda"
    
    # --- Contract patterns ---
    def test_contract_purchase_orders(self, classifier):
        """Test 'purchase orders' keyword (EVTV case)."""
        result = classifier.classify("AZIO receives $100 Million worth of Government Purchase Orders")
        assert result.is_positive is True
        assert result.catalyst_type == "contract"
    
    def test_contract_receives_million(self, classifier):
        """Test 'receives $X million' pattern."""
        result = classifier.classify("Company receives $50 million contract from DoD")
        assert result.is_positive is True
        assert result.catalyst_type == "contract"
    
    def test_contract_supplies_to(self, classifier):
        """Test 'supplies to' keyword (UAVS case)."""
        result = classifier.classify("EagleNXT Supplies Drones to NATO Forces in Europe")
        assert result.is_positive is True
        assert result.catalyst_type == "contract"
    
    def test_contract_government_order(self, classifier):
        """Test 'government order' keyword."""
        result = classifier.classify("Awarded major government order worth $200M")
        assert result.is_positive is True
        assert result.catalyst_type == "contract"
    
    # --- Earnings patterns ---
    def test_earnings_preliminary_quarter(self, classifier):
        """Test 'preliminary fourth quarter' keyword (BDSX case)."""
        result = classifier.classify("Biodesix Announces Preliminary Fourth Quarter and Full-Year 2025 Results")
        assert result.is_positive is True
        assert result.catalyst_type == "earnings"
    
    def test_earnings_full_year(self, classifier):
        """Test 'full-year results' keyword."""
        result = classifier.classify("Company reports strong full-year results")
        assert result.is_positive is True
        assert result.catalyst_type == "earnings"
    
    # --- Negative cases (should NOT match) ---
    def test_no_catalyst_generic_news(self, classifier):
        """Test generic news doesn't match."""
        result = classifier.classify("Shares Pass Below 200 Day Moving Average")
        assert result.is_positive is False
    
    def test_no_catalyst_product_launch(self, classifier):
        """Test product launch without catalyst keywords."""
        result = classifier.classify("Sleep Number Introduces ComfortMode Mattress")
        # This shouldn't match as a strong catalyst
        assert result.confidence < 0.6 or result.catalyst_type is None
