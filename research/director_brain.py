"""
Project: The Director (Feedback Loop)
Version: 1.0.0
Author: Gemini (Assistant) & [Your Name]
"""
import os
from dotenv import load_dotenv
import google.generativeai as genai
from backtest_lab import run_test  # Import your actual backtester

# 1. SETUP
load_dotenv()
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
MODEL_NAME = "gemini-2.5-flash"


def get_critique(current_strategy_text, stats):
    """
    The Director AI reviews the performance and gives harsh, specific feedback.
    """
    print("\n🎬 DIRECTOR IS REVIEWING PERFORMANCE...")

    director_prompt = (
        "You are a hedge fund Risk Manager. You are reviewing a failed trading strategy. "
        "Your goal is to pinpoint WHY it failed and propose a specific mathematical fix. "
        "\n\n"
        f"--- CURRENT STRATEGY ---\n{current_strategy_text}\n\n"
        "--- PERFORMANCE REPORT ---\n"
        f"Ticker: {stats._strategy}\n"
        f"Return: {stats['Return [%]']:.2f}% (vs Buy&Hold: {stats['Buy & Hold Return [%]']:.2f}%)\n"
        f"Win Rate: {stats['Win Rate [%]']:.2f}%\n"
        f"Max Drawdown: {stats['Max. Drawdown [%]']:.2f}%\n"
        f"Trades: {stats['# Trades']}\n\n"
        "--- ANALYSIS REQUIRED ---\n"
        "1. Diagnose the failure (e.g., 'Over-trading in choppy markets', 'Stop loss too tight').\n"
        "2. Propose a SPECIFIC fix (e.g., 'Add a Volume Filter > 200% average', 'Use RSI < 30 for entry').\n"
        "3. Output the REVISED strategy description for the coder."
    )

    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(director_prompt)
    return response.text


# ==============================================================================
# MAIN LOOP
# ==============================================================================
if __name__ == "__main__":
    # 1. Define what we are testing (This mimics what the Manager wrote previously)
    current_strategy = "Buy when Close > 10SMA and 10SMA > 50SMA. Sell when Close < 10SMA."

    # 2. Run the actual Backtest (The "Test")
    # We test on ALTO since we know it failed there
    try:
        real_stats = run_test("ALTO")
    except Exception as e:
        print(f"Backtest failed: {e}")
        exit()

    # 3. Check if it passed the "Bar"
    # Goals: Positive Return AND Profit Factor > 1.5
    if real_stats['Return [%]'] > 0 and real_stats['Profit Factor'] > 1.5:
        print("\n✅ STRATEGY PASSED! No changes needed.")
    else:
        print("\n❌ STRATEGY FAILED. Initiating Feedback Loop...")

        # 4. The Director Critiques
        feedback = get_critique(current_strategy, real_stats)

        print("\n" + "=" * 40)
        print("📝 DIRECTOR'S IMPROVEMENT PLAN")
        print("=" * 40)
        print(feedback)