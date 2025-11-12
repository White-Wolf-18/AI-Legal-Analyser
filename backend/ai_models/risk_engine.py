import re
import json
from typing import Dict, List, Tuple, Any
# from models.user import LegalStatute
# from sqlalchemy import func
import spacy
from transformers import pipeline
import logging

class AdvancedRiskEngine:
    def __init__(self, db_session):
        self.db = db_session
        self.nlp = spacy.load("en_core_web_sm")
        self.statute_cache = self._load_statutes()
        
        # Initialize legal reference pipeline
        self.legal_reference_pipeline = pipeline(
            "question-answering",
            model="deepset/roberta-base-squad2"
        )
        
        # Define dynamic risk patterns with explanations
        self.risk_patterns = {
            'high': [
                {
                    'pattern': r'unlimited.*liability',
                    'explanation': 'Unlimited liability clauses can expose parties to excessive financial risk beyond reasonable bounds',
                    'statute_reference': 'Indian Contract Act, 1872 - Section 73: Compensation for breach of contract'
                },
                {
                    'pattern': r'forfeit.*deposit',
                    'explanation': 'Deposit forfeiture clauses without proper justification can be legally challenged',
                    'statute_reference': 'Transfer of Property Act, 1882 - Deposit refund obligations'
                },
                {
                    'pattern': r'compulsory.*bond',
                    'explanation': 'Compulsory bonds may violate labor laws and employee rights',
                    'statute_reference': 'Industrial Disputes Act, 1947 - Employee rights and obligations'
                },
                {
                    'pattern': r'non-compete.*period.*\d+.*years?',
                    'explanation': 'Excessive non-compete periods may be unenforceable in Indian courts',
                    'statute_reference': 'Indian Contract Act, 1872 - Section 27: Restraint of trade'
                },
                {
                    'pattern': r'penalty.*\d+%',
                    'explanation': 'High penalty rates may be considered excessive and void under Indian law',
                    'statute_reference': 'Indian Contract Act, 1872 - Section 74: Penalty for breach of contract'
                }
            ],
            'medium': [
                {
                    'pattern': r'reasonable.*time',
                    'explanation': 'Ambiguous "reasonable" timeframes can lead to disputes and legal uncertainty',
                    'statute_reference': 'Indian Contract Act, 1872 - Section 55: Impossibility of performance'
                },
                {
                    'pattern': r'subject.*to.*change',
                    'explanation': 'Terms subject to change without notice can create contractual instability',
                    'statute_reference': 'Indian Contract Act, 1872 - Section 62: Alteration of contracts'
                },
                {
                    'pattern': r'may.*modify',
                    'explanation': 'Unilateral modification rights without consent can be problematic',
                    'statute_reference': 'Indian Contract Act, 1872 - Section 62: Alteration of contracts'
                },
                {
                    'pattern': r'at.*discretion',
                    'explanation': 'Vague discretion clauses can lead to arbitrary enforcement',
                    'statute_reference': 'Indian Contract Act, 1872 - Section 56: Void agreements'
                }
            ],
            'low': [
                {
                    'pattern': r'as.*per.*law',
                    'explanation': 'Standard legal compliance clauses are generally acceptable',
                    'statute_reference': 'Constitution of India - Article 14: Equality before law'
                },
                {
                    'pattern': r'fair.*practice',
                    'explanation': 'Fair practice clauses are generally acceptable but may need specific definition',
                    'statute_reference': 'Consumer Protection Act, 2019 - Fair trade practices'
                }
            ]
        }

    def _load_statutes(self):
        """Load sample legal statutes (in-memory, no DB)."""
        return {
            "Indian Contract Act, 1872 - Section 73": {
                "section": "Section 73",
                "description": "Compensation for loss or damage caused by breach of contract",
                "keywords": ["breach", "compensation", "damages", "loss"],
                "applicable_clauses": ["loan", "employment", "rental"]
            },
            "Indian Contract Act, 1872 - Section 27": {
                "section": "Section 27",
                "description": "Agreement in restraint of trade is void",
                "keywords": ["non-compete", "trade", "restraint"],
                "applicable_clauses": ["employment", "partnership"]
            },
            "Indian Contract Act, 1872 - Section 74": {
                "section": "Section 74",
                "description": "Penalty for breach of contract",
                "keywords": ["penalty", "fine", "default"],
                "applicable_clauses": ["loan", "employment", "rental"]
            }
        }


    def analyze_risk_with_statutes(self, clause: str, clause_type: str) -> Dict:
        """Analyze risk by cross-referencing against Indian legal statutes"""
        clause_lower = clause.lower()
        
        # Get relevant statutes for this clause type
        relevant_statutes = []
        for name, statute in self.statute_cache.items():
            if clause_type in statute['applicable_clauses']:
                relevant_statutes.append((name, statute))

        # Analyze against predefined patterns
        pattern_violations = self._analyze_pattern_violations(clause)
        
        # Analyze against statutes
        statute_violations = []
        compliance_issues = []
        legal_references = []

        for statute_name, statute_info in relevant_statutes:
            for keyword in statute_info['keywords']:
                if keyword.lower() in clause_lower:
                    violation_analysis = self._analyze_keyword_context(
                        clause, keyword.lower(), statute_info
                    )
                    
                    if violation_analysis['is_violation']:
                        statute_violations.append({
                            'statute': statute_name,
                            'section': statute_info['section'],
                            'violation': violation_analysis['violation_description'],
                            'keyword': keyword,
                            'severity': violation_analysis['severity'],
                            'explanation': violation_analysis['explanation']
                        })
                    elif violation_analysis['compliance_issue']:
                        compliance_issues.append({
                            'statute': statute_name,
                            'section': statute_info['section'],
                            'issue': violation_analysis['compliance_description'],
                            'keyword': keyword,
                            'explanation': violation_analysis['explanation']
                        })
            
            legal_references.append({
                'statute': statute_name,
                'section': statute_info['section'],
                'description': statute_info['description'],
                'relevance_score': self._calculate_relevance(clause, statute_info['keywords'])
            })

        # Combine pattern and statute analysis
        all_violations = pattern_violations + statute_violations
        
        # Calculate risk score based on violations and compliance issues
        high_violations = len([v for v in all_violations if v.get('severity') == 'high'])
        medium_violations = len([v for v in all_violations if v.get('severity') == 'medium'])
        compliance_issues_count = len(compliance_issues)
        
        risk_score = min((high_violations * 0.4 + medium_violations * 0.2 + compliance_issues_count * 0.1), 1.0)

        if risk_score >= 0.7:
            risk_level = 'high'
        elif risk_score >= 0.3:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        return {
            'risk_level': risk_level,
            'risk_score': risk_score,
            'violations': all_violations,
            'compliance_issues': compliance_issues,
            'legal_references': legal_references,
            'statute_references': [statute_name for statute_name, _ in relevant_statutes],
            'pattern_violations': pattern_violations
        }

    def _analyze_pattern_violations(self, clause: str) -> List[Dict]:
        """Analyze clause against predefined risk patterns"""
        violations = []
        clause_lower = clause.lower()
        
        for severity, patterns in self.risk_patterns.items():
            for pattern_info in patterns:
                if re.search(pattern_info['pattern'], clause_lower, re.IGNORECASE):
                    violations.append({
                        'type': 'pattern_violation',
                        'severity': severity,
                        'pattern': pattern_info['pattern'],
                        'explanation': pattern_info['explanation'],
                        'statute_reference': pattern_info['statute_reference'],
                        'violation_description': f"Pattern violation: {pattern_info['explanation']}"
                    })
        
        return violations

    def _analyze_keyword_context(self, clause: str, keyword: str, statute_info: Dict) -> Dict:
        """Analyze the context of a keyword to determine if it's a violation or compliance issue"""
        clause_lower = clause.lower()
        
        # Define violation patterns that indicate non-compliance
        violation_patterns = [
            r'contrary to',
            r'not in accordance with',
            r'without following',
            r'despite requirements',
            r'except when',
            r'subject to.*violation',
            f'not {keyword}',
            f'without {keyword}',
        ]
        
        # Define compliance issue patterns (ambiguous or non-specific language)
        compliance_patterns = [
            r'not clearly defined',
            r'not specified',
            r'at discretion',
            r'as required',
            r'if necessary',
            r'when possible',
            r'reasonable.*time',
            r'appropriate.*action',
            r'subject to.*change',
            r'may.*modify',
        ]
        
        # Check for violations
        for pattern in violation_patterns:
            if re.search(pattern, clause_lower, re.IGNORECASE):
                return {
                    'is_violation': True,
                    'violation_description': f"Potential violation of {statute_info['section']}: Clause may contradict {statute_info['section']}",
                    'compliance_issue': False,
                    'severity': 'high',
                    'explanation': f"This clause appears to contradict {statute_info['section']} of {statute_info['description']}. This could render the clause unenforceable."
                }
        
        # Check for compliance issues
        for pattern in compliance_patterns:
            if re.search(pattern, clause_lower, re.IGNORECASE):
                return {
                    'is_violation': False,
                    'violation_description': '',
                    'compliance_issue': True,
                    'compliance_description': f"Compliance issue with {statute_info['section']}: Clause contains ambiguous language",
                    'severity': 'medium',
                    'explanation': f"The clause contains ambiguous language that doesn't clearly comply with {statute_info['section']}. This could lead to legal disputes."
                }
        
        # Check for positive compliance indicators
        compliance_indicators = [
            r'in accordance with',
            r'as per',
            r'compliant with',
            r'pursuant to',
            f'under {statute_info["section"]}',
        ]
        
        for indicator in compliance_indicators:
            if re.search(indicator, clause_lower, re.IGNORECASE):
                return {
                    'is_violation': False,
                    'violation_description': '',
                    'compliance_issue': False,
                    'compliance_description': '',
                    'severity': 'low',
                    'explanation': f"The clause appears to comply with {statute_info['section']} of {statute_info['description']}."
                }
        
        # Default: no clear violation or compliance
        return {
            'is_violation': False,
            'violation_description': '',
            'compliance_issue': True,
            'compliance_description': f"Review needed: Clause may not clearly reference {statute_info['section']}",
            'severity': 'low',
            'explanation': f"The clause doesn't explicitly reference {statute_info['section']}. Consider adding specific legal references for clarity."
        }

    def get_legal_references(self, clause: str, clause_type: str) -> List[Dict]:
        """Get legal references for a clause"""
        legal_refs = []
        
        # Find relevant statutes
        for name, info in self.statute_cache.items():
            if clause_type in info['applicable_clauses']:
                legal_refs.append({
                    'statute': name,
                    'section': info['section'],
                    'description': info['description'],
                    'relevance_score': self._calculate_relevance(clause, info['keywords'])
                })
        
        # Sort by relevance
        legal_refs.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return legal_refs[:5]  # Return top 5 references

    def _calculate_relevance(self, clause: str, keywords: List[str]) -> float:
        """Calculate relevance score based on keyword matching and context"""
        clause_lower = clause.lower()
        matches = sum(1 for keyword in keywords if keyword.lower() in clause_lower)
        
        total_keywords = len(keywords) if keywords else 1
        base_score = matches / total_keywords
        
        # Boost score if important legal terms are present
        important_terms = ['shall', 'must', 'required', 'obligated', 'compelled', 'notwithstanding']
        important_matches = sum(1 for term in important_terms if term in clause_lower)
        
        return min(base_score + (important_matches * 0.1), 1.0)

    def generate_dynamic_recommendations(self, clause: str, risk_analysis: Dict, legal_refs: List[Dict]) -> List[str]:
        """Generate dynamic, context-specific recommendations based on the actual clause content"""
        recommendations = []
        
        # Generate specific recommendations based on detected violations
        for violation in risk_analysis['violations']:
            if violation.get('type') == 'pattern_violation':
                recommendations.append(f"⚠️ CRITICAL: {violation['violation_description']}")
                recommendations.append(f"   - Legal Reference: {violation['statute_reference']}")
                recommendations.append(f"   - Action: This clause should be revised to comply with legal requirements.")
            else:
                recommendations.append(f"⚠️ CRITICAL: {violation['violation_description']}")
                recommendations.append(f"   - Explanation: {violation['explanation']}")
        
        # Generate compliance recommendations
        for issue in risk_analysis['compliance_issues']:
            recommendations.append(f"⚠️ REVIEW: {issue['issue']}")
            recommendations.append(f"   - Explanation: {issue['explanation']}")
        
        # Generate general recommendations based on clause type
        type_specific_recommendations = self._get_clause_type_specific_recommendations(
            risk_analysis['violations'], 
            risk_analysis['compliance_issues'],
            risk_analysis.get('pattern_violations', [])
        )
        recommendations.extend(type_specific_recommendations)
        
        # Add general legal best practices
        recommendations.extend([
            "• Have this clause reviewed by a qualified legal professional",
            "• Ensure all terms are clearly defined and unambiguous",
            "• Verify that the clause aligns with current Indian legal requirements",
            "• Consider including specific legal references to relevant statutes",
            "• Ensure mutual consent and fairness in all contractual terms"
        ])
        
        return recommendations

    def _get_clause_type_specific_recommendations(self, violations: List[Dict], compliance_issues: List[Dict], pattern_violations: List[Dict]) -> List[str]:
        """Generate clause-type-specific recommendations"""
        recommendations = []
        
        # Check for specific pattern violations to generate targeted advice
        high_risk_patterns = [v for v in pattern_violations if v['severity'] == 'high']
        medium_risk_patterns = [v for v in pattern_violations if v['severity'] == 'medium']
        
        for violation in high_risk_patterns:
            if 'unlimited liability' in violation['explanation'].lower():
                recommendations.append("• Consider capping liability to a reasonable amount to protect against excessive claims")
            elif 'forfeit deposit' in violation['explanation'].lower():
                recommendations.append("• Ensure deposit forfeiture has proper justification and follows local tenancy laws")
            elif 'non-compete' in violation['explanation'].lower():
                recommendations.append("• Limit non-compete period to maximum 2-3 years and specify geographic scope")
        
        for violation in medium_risk_patterns:
            if 'reasonable time' in violation['explanation'].lower():
                recommendations.append("• Define specific timeframes instead of using ambiguous terms like 'reasonable time'")
            elif 'subject to change' in violation['explanation'].lower():
                recommendations.append("• Specify notice period and approval process for any changes")
        
        # Check for compliance issues
        for issue in compliance_issues:
            if 'ambiguous' in issue['explanation'].lower():
                recommendations.append("• Clarify ambiguous terms with specific definitions and measurable criteria")
        
        return recommendations

    def generate_dynamic_summary(self, text: str, clause_type: str) -> str:
        """Generate a dynamic summary that adapts to the clause type and content"""
        # Use the enhanced summarization from IndianLegalBERT
        from .indian_legal_bert import IndianLegalBERT
        
        # Create a temporary instance to use the summarization method
        temp_bert = IndianLegalBERT()
        summary = temp_bert.generate_dynamic_summary(text)
        
        # Enhance the summary based on clause type
        if clause_type == 'rental':
            summary += " This rental agreement clause defines tenant and landlord obligations regarding rent, security deposits, and property usage."
        elif clause_type == 'employment':
            summary += " This employment clause outlines worker responsibilities, compensation terms, and termination conditions."
        elif clause_type == 'divorce':
            summary += " This clause addresses maintenance, custody, and property division in divorce proceedings."
        elif clause_type == 'property':
            summary += " This property clause covers ownership rights, transfer procedures, and registration requirements."
        
        return summary