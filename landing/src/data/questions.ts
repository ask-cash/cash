// Questions for the "Get access" waitlist flow.
export type QuestionType = 'single' | 'multi' | 'text' | 'email'

export interface Question {
  id: string
  type: QuestionType
  q: string
  sub?: string
  options?: string[]
  logos?: boolean
  placeholder?: string
  optional?: boolean
}

export const QUESTIONS: Question[] = [
  {
    id: 'role',
    type: 'single',
    q: 'First — what best describes you?',
    sub: 'So Cash calibrates to how you work and what you will need most.',
    options: ['Founder', 'Investor', 'Operator / PM', 'Engineer', 'Student', 'Something else'],
  },
  {
    id: 'use',
    type: 'multi',
    q: 'What should Cash run for you?',
    sub: 'Pick all that apply — this shapes your first week.',
    options: [
      'Financial intelligence',
      'Calendar & meetings',
      'Inbox & communication',
      'Research',
      'Engineering',
      'All of it',
    ],
  },
  {
    id: 'tools',
    type: 'multi',
    q: 'Which tools do you live in?',
    sub: 'We will prioritize these connections for you.',
    options: ['Slack', 'Gmail', 'Google Calendar', 'Notion', 'GitHub', 'Telegram', 'Coinbase', 'TradingView'],
    logos: true,
  },
  {
    id: 'priority',
    type: 'text',
    q: 'What is the one thing you would hand off today?',
    sub: 'Optional — but it helps us set Cash up around you.',
    placeholder: 'e.g. my inbox, the morning market brief, scheduling…',
    optional: true,
  },
  {
    id: 'name',
    type: 'text',
    q: 'Great. What should Cash call you?',
    sub: 'Your name, so the welcome feels less robotic.',
    placeholder: 'Suhail',
  },
  {
    id: 'email',
    type: 'email',
    q: 'Last step — where should we send your invite?',
    sub: 'No spam, ever. Just your access the moment it opens.',
    placeholder: 'you@company.com',
  },
]
