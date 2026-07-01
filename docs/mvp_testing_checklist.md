# FAR Bot MVP Testing - Critical Requirements Only

## Overview
This is the essential testing checklist for FAR Bot MVP launch. These are the **must-pass** items before going live.

## Critical MVP Testing Checklist

### 🔧 System Startup (Blocking Issues)
- [ ] Run `setup_check.py` - system validates without errors
- [ ] API keys work (OpenAI connection successful)
- [ ] FAISS index loads and is accessible
- [ ] Web interface loads without crashes

### 🎯 Core Functionality (Must Work)
- [ ] **Basic FAR Q&A**: Ask 5 simple FAR questions, get accurate responses with citations
- [ ] **Search Quality**: Test search across FAR Parts 1, 15, 25, 52 (most common)
- [ ] **Citation Accuracy**: Verify 10 responses have correct FAR section references
- [ ] **Out-of-scope handling**: Non-FAR questions get appropriate "not in scope" responses

### ⚡ Performance (User Experience)
- [ ] Response time <15 seconds for typical queries
- [ ] System handles 3 concurrent users without crashes
- [ ] Memory usage stable during 30-minute session

### 🔒 Security Basics (Risk Mitigation)
- [ ] API keys not exposed in responses or logs
- [ ] Basic input sanitization (no system crashes from long/weird inputs)
- [ ] Legal disclaimer appears in responses

### 👥 User Validation (Acceptance)
- [ ] **FAR team validation**: 3 FAR experts test with real questions
- [ ] **Accuracy check**: 90%+ accuracy on 20 test questions from FAR team
- [ ] **Usability**: Users can complete typical workflow without assistance

## Success Criteria for MVP Launch
- ✅ All "Blocking Issues" resolved
- ✅ Core functionality works reliably
- ✅ FAR team approves accuracy and usefulness
- ✅ No critical security vulnerabilities
- ✅ Performance meets minimum thresholds

## Test Execution Priority
1. **Day 1**: System startup and basic functionality
2. **Day 2**: Performance and security basics
3. **Day 3**: FAR team validation and user testing

## Red Flags (Do Not Launch)
- ❌ Incorrect FAR citations in responses
- ❌ System crashes under normal use
- ❌ Response times >30 seconds regularly
- ❌ FAR experts identify accuracy concerns
- ❌ API keys or sensitive data exposed

## Post-MVP Testing (Can Wait)
- Advanced security testing
- Load testing beyond 3 users
- Mobile optimization
- Accessibility compliance
- Complex multi-turn conversations
- Edge case handling

---
**This checklist focuses on launch-critical items only. Full testing plan available in `testing_plan.md`**