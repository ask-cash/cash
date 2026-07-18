// Onboarding profile questions asked right after signup.
export interface OnboardingQuestion {
  id: 'role' | 'platforms'
  type: 'single' | 'multi'
  q: string
  sub: string
  options: string[]
  logos?: boolean
}

export const ONBOARDING: OnboardingQuestion[] = [
  {
    id: 'role',
    type: 'single',
    q: 'What best describes you?',
    sub: 'So Cash calibrates to how you work and what you need most.',
    options: ['Founder', 'Product Manager', 'Engineer', 'Student', 'Designer', 'Marketer', 'Other'],
  },
  {
    id: 'platforms',
    type: 'multi',
    q: 'Which platforms do you currently use?',
    sub: "Pick all that apply — we'll prioritise connecting these.",
    options: [
      'Slack',
      'Microsoft Teams',
      'Google Calendar',
      'Telegram',
      'Discord',
      'TradingView',
      'Brokers',
      'Other',
    ],
    logos: true,
  },
]
