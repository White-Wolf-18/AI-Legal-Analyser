from transformers import AutoTokenizer, AutoModelForSequenceClassification, TrainingArguments, Trainer
from transformers import DataCollatorWithPadding, pipeline
import torch
import pandas as pd
from datasets import Dataset
import json
import os
import re
from typing import List, Dict, Tuple

class IndianLegalBERT:
    def __init__(self, model_path="./models/indian_legal_bert"):
        """Initialize with fine-tuned model"""
        self.model_path = model_path
        if os.path.exists(model_path):
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
            
            # Load label mapping
            with open(f"{model_path}/label_mapping.json", 'r') as f:
                label_mapping = json.load(f)
            
            self.id_to_label = {int(k): v for k, v in label_mapping['id_to_label'].items()}
            self.label_to_id = {v: int(k) for k, v in label_mapping['label_to_id'].items()}
        else:
            # Fallback to base model if fine-tuned model doesn't exist
            self.model_name = "nlpaueb/legal-bert-base-uncased"
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name,
                num_labels=10
            )
            self.label_names = [
                'rental', 'divorce', 'employment', 'loan',
                'consumer', 'property', 'partnership',
                'privacy', 'insurance', 'freelancer'
            ]
            self.id_to_label = {i: label for i, label in enumerate(self.label_names)}
            self.label_to_id = {label: i for i, label in enumerate(self.label_names)}
        
        # Initialize text generation pipeline for summaries
        self.summarizer = pipeline(
            "text2text-generation",
            model="facebook/bart-large-cnn",
            tokenizer="facebook/bart-large-cnn",
            device=0 if torch.cuda.is_available() else -1
        )

    def predict_clause_type(self, text):
        """Predict clause type for a given text"""
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=512
        )
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            predicted_class = torch.argmax(predictions, dim=-1).item()
            confidence = predictions[0][predicted_class].item()
        
        return self.id_to_label[predicted_class], confidence

    def generate_dynamic_summary(self, text: str, max_length: int = None) -> str:
        """Generate a dynamic summary that adapts to document length and complexity"""
        # Calculate optimal summary length based on document length
        if max_length is None:
            # Base length on input text length (10-15% of original length)
            base_length = len(text.split()) // 8  # 12.5% of original
            max_length = max(50, min(base_length, 200))  # Between 50-200 words
        
        min_length = max(30, max_length // 2)  # At least 50% of max length
        
        try:
            # Use BART for better legal text summarization
            summary = self.summarizer(
                text,
                max_length=max_length,
                min_length=min_length,
                do_sample=False,
                truncation=True
            )[0]['generated_text']
            
            # Post-process to make it more readable for legal documents
            summary = self._post_process_summary(summary, text)
            
            return summary
        except Exception as e:
            # Fallback to simple extraction if generation fails
            return self._fallback_summary(text, max_length)

    def _post_process_summary(self, summary: str, original_text: str) -> str:
        """Post-process the summary to make it more legal-appropriate"""
        # Fix common BART artifacts in legal text
        summary = re.sub(r'\s+', ' ', summary.strip())
        
        # Ensure key legal terms are preserved
        legal_keywords = ['shall', 'must', 'required', 'obligated', 'compelled', 'notwithstanding', 'provided that']
        for keyword in legal_keywords:
            if keyword in original_text and keyword not in summary:
                # Try to include the concept in the summary
                sentences = original_text.split('.')
                for sentence in sentences[:3]:  # Check first few sentences
                    if keyword in sentence:
                        summary += f" Additionally, {sentence.strip()}."
                        break
        
        # Capitalize first letter
        if summary:
            summary = summary[0].upper() + summary[1:]
        
        return summary

    def _fallback_summary(self, text: str, max_length: int) -> str:
        """Fallback method to extract key sentences"""
        sentences = text.split('.')
        # Take first few sentences that contain important legal terms
        important_sentences = []
        legal_indicators = ['shall', 'must', 'required', 'obligated', 'compelled', 'notwithstanding', 'provided']
        
        for sentence in sentences:
            if any(indicator in sentence.lower() for indicator in legal_indicators):
                important_sentences.append(sentence.strip())
            elif len(important_sentences) < 3:  # Take up to 3 additional sentences
                important_sentences.append(sentence.strip())
        
        return '. '.join(important_sentences[:5]) + '.' if important_sentences else text[:200] + "..."

    def batch_predict(self, texts):
        """Batch prediction for multiple texts"""
        inputs = self.tokenizer(
            texts,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=512
        )
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            predicted_classes = torch.argmax(predictions, dim=-1)
            confidences = torch.max(predictions, dim=-1)[0]
        
        results = []
        for i, (pred_class, conf) in enumerate(zip(predicted_classes, confidences)):
            results.append({
                'clause_type': self.id_to_label[pred_class.item()],
                'confidence': conf.item()
            })
        
        return results

    def load_fine_tuned_model(self, model_path):
        """Load a fine-tuned model"""
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        
        # Load updated label mapping
        with open(f"{model_path}/label_mapping.json", 'r') as f:
            label_mapping = json.load(f)
        
        self.id_to_label = {int(k): v for k, v in label_mapping['id_to_label'].items()}
        self.label_to_id = {v: int(k) for k, v in label_mapping['label_to_id'].items()}

    def get_relevant_law(self, clause_type: str):
        """Return the most relevant Indian law based on clause type or keyword"""
        mapping = {
            "liability": "Indian Contract Act, 1872 (Sections 73–75)",
            "interest": "Indian Contract Act, 1872 (Section 23 – Lawful consideration)",
            "security": "SARFAESI Act, 2002 (Section 13 – Enforcement of security interest)",
            "confidentiality": "Information Technology Act, 2000 (Section 72 – Breach of confidentiality and privacy)",
            "employment": "Industrial Disputes Act, 1947 (Employee rights and obligations)",
            "termination": "Indian Contract Act, 1872 (Section 39 – Effect of refusal to perform promise)",
            "penalty": "Indian Contract Act, 1872 (Section 74 – Penalty for breach of contract)"
        }
        return mapping.get(clause_type.lower(), "Indian Contract Act, 1872")

    def generate_improved_clause(self, clause: str, clause_type: str) -> str:
        """
        Generate a legally safe & improved version of the clause.
        This uses NLP heuristics + light rephrasing to reduce risk.
        """
        base = clause.strip()

        # Basic transformations
        base = re.sub(r"\bshall\b", "will", base, flags=re.IGNORECASE)
        base = re.sub(r"\bpenal\b|\bpenalty\b", "reasonable fee", base, flags=re.IGNORECASE)
        base = re.sub(r"\bterminate at its sole discretion\b", 
                      "terminate under reasonable circumstances with written notice",
                      base, flags=re.IGNORECASE)

        # Standard safe wording templates
        safety_templates = {
            "penalty": "Any charges imposed shall be reasonable, proportionate and compliant with Section 74 of the Indian Contract Act, 1872.",
            "non-compete": "Any restriction shall be reasonable in duration and scope, ensuring compliance with Section 27 of the Indian Contract Act, 1872.",
            "termination": "Either party may terminate this agreement with written notice, subject to reasonable grounds and applicable law."
        }

        improved = base
    
        # Add legal-compliant safety lines
        if "penalty" in clause.lower():
            improved += "\n\n" + safety_templates["penalty"]

        if "non-compete" in clause.lower() or "restraint" in clause.lower():
            improved += "\n\n" + safety_templates["non-compete"]
 
        if "terminate" in clause.lower():
            improved += "\n\n" + safety_templates["termination"]

        return improved.strip()
    

    # ai_models/indian_legal_bert.py (inside class IndianLegalBERT)

    def rewrite_clause(self, clause_text: str, clause_type: str = None, max_length: int = 160) -> str:
        """
        Produce an improved, lower-risk rewrite of a clause.
        - Keep original intent
        - Make obligations/timeframes concrete
        - Remove blanket waivers / absolute seizure language
        - Cap excessive penalty/interest values where possible by suggestion
        Returns the rewritten clause as plain text. Falls back to rule-based adjustments if generation fails.
        """
        # Safety-first short circuit
        if not clause_text or len(clause_text.strip()) < 20:
            return clause_text

        # Prompt engineering: explicit instructions
        instructions = (
            "Rewrite the following *single legal clause* so it is enforceable under Indian commercial law, "
            "while preserving the original commercial intent. Do NOT add new obligations that change the intent. "
            "Make deadlines concrete, replace absolute or one-sided language with balanced wording, "
            "cap penalty or interest rates to reasonable commercial norms if the clause uses excessive percentages, "
            "limit non-compete periods to a maximum of 2 years and specify geographic scope, "
            "remove blanket waivers of legal rights, and require notice & cure periods before remedies. "
            "Return ONLY the rewritten clause (one paragraph)."
        )

        prompt = f"{instructions}\n\nClause:\n{clause_text}\n\nRewritten clause:"

        try:
            out = self.summarizer(
                prompt,
                max_length=max_length,
                min_length=40,
                do_sample=False,
                truncation=True
            )
            gen = out[0].get("generated_text") or out[0].get("summary_text") or ""
            gen = gen.strip()

            # Post-processing heuristics:
            # If generator left an obviously excessive percentage, reduce it programmatically.
            def _cap_percentages(s):
                def repl(m):
                    val = int(m.group(1))
                    unit = m.group(2) or ""
                    # business rule caps: monthly rates > 10% -> replace, annual > 60% -> replace
                    if "month" in unit or "per month" in unit:
                        if val > 10:
                            return "10% per month /* capped from {}% */".format(val)
                    else:
                        if val > 60:
                            return "36% per annum /* capped from {}% */".format(val)
                    return f"{val}% {unit}".strip()
                return re.sub(r"(\d{1,3})\s*%\s*(per\s*month|per\s*annum|monthly|annually)?", repl, s, flags=re.IGNORECASE)
 
            gen = _cap_percentages(gen)

            # Ensure we didn't return instructions back
            gen = re.sub(r"^Rewritten clause:\s*", "", gen, flags=re.IGNORECASE).strip()

            # Final truncate to reasonable length
            if len(gen) > 800:
                gen = gen[:800].rsplit('.', 1)[0] + '.'

            return gen
        except Exception as e:
            # Fallback: simple rule-based safer rewrite (best-effort)
            clause = clause_text

            # Remove "without notice" madness
            clause = re.sub(r"\bwithout (prior|any) notice\b", "after a written notice and 7 business days' opportunity to cure", clause, flags=re.IGNORECASE)

            # Replace blanket waivers
            clause = re.sub(r"\b(waive|waives|waived)\s+(all )?(rights|claims|remedies)\b", "notwithstanding the foregoing, the party shall not waive any mandatory statutory rights", clause, flags=re.IGNORECASE)

            # Cap very high percentages heuristically
            def cap_percent_fallback(m):
                v = int(m.group(1))
                if v > 60:
                    return "36% per annum"
                if v > 10 and 'month' in (m.group(2) or ""):
                    return "10% per month"
                return m.group(0)
            clause = re.sub(r"(\d{1,3})\s*%\s*(per\s*month|per\s*annum|monthly|annually)?", cap_percent_fallback, clause, flags=re.IGNORECASE)
  
            # Limit non-compete durations > 2 years
            clause = re.sub(r"non-?compete.*\b(\d{1,2})\s*(years?)\b", "non-compete limited to 2 years in a defined geographic area reasonably required to protect legitimate business interests", clause, flags=re.IGNORECASE)

            return clause


