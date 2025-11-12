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