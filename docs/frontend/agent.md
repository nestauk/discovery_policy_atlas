# Agent interface

The agent interface provides an AI-powered research query refinement workflow.

## Flow Overview

**Query Input** (`/agent`)

   - User enters free text research question

**AI Refinement** (`/agent/options`)

   - Backend generates 3 refined query suggestions using OpenAI
   - User can select original query or any refinement

**Results** (`/agent/results`)

   - Displays search results with tabs for summary, evidence, policy, etc.
   - Mock data currently - integration with backend search APIs pending
