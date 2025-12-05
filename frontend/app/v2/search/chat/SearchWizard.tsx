"use client";

import React, { useState } from "react";
import { create } from "zustand";
import { useAPI } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Tooltip } from '@/components/ui/tooltip';

// ---------------- UI PRIMITIVES ----------------
const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(" ");
const Card = ({ children, className = "" }: React.PropsWithChildren<{ className?: string }>) => (
  <div className={cx("rounded-2xl bg-white shadow-sm ring-1 ring-gray-200/60", className)}>{children}</div>
);
const CardHeader = ({ children }: React.PropsWithChildren) => (
  <div className="p-5 border-b border-gray-100 rounded-t-2xl bg-gray-50/60">{children}</div>
);
const CardTitle = ({ children, className = "" }: React.PropsWithChildren<{ className?: string }>) => (
  <h3 className={cx("font-semibold text-lg", className)}>{children}</h3>
);
const CardContent = ({ children, className = "" }: React.PropsWithChildren<{ className?: string }>) => (
  <div className={cx("p-5", className)}>{children}</div>
);
const Button = ({ children, onClick, disabled, variant = "primary", className = "", full = false }: { children: React.ReactNode; onClick?: () => void; disabled?: boolean; variant?: "primary" | "secondary" | "ghost"; className?: string; full?: boolean; }) => (
  <button onClick={onClick} disabled={disabled} className={cx("rounded-xl px-5 py-3 font-medium transition", full && "w-full", variant === "primary" && "bg-blue-600 !text-white hover:bg-blue-700 disabled:opacity-50", variant === "secondary" && "bg-white text-gray-900 ring-1 ring-gray-300 hover:bg-gray-50", variant === "ghost" && "bg-transparent text-gray-700 hover:bg-gray-100", className)}>{children}</button>
);
const Textarea = (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea {...props} className={cx("w-full text-xl leading-7 p-6 rounded-2xl ring-1 ring-gray-300 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-600", props.className)} />
);
const Input = (props: React.InputHTMLAttributes<HTMLInputElement>) => (
  <input {...props} className={cx("w-full rounded-xl ring-1 ring-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-600", props.className)} />
);
const Chip = ({ active, children, onClick }: { active?: boolean; children: React.ReactNode; onClick?: () => void }) => (
  <button type="button" onClick={onClick} className={cx("px-3 py-2 rounded-full text-sm transition ring-1", active ? "bg-blue-600 !text-white ring-blue-600" : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50")}>{children}</button>
);

// ---------------- TYPES & CONSTANTS ----------------
type Step = "ASK" | "POPULATION" | "OUTCOME" | "PARAMETERS" | "SCREENING" | "ADDITIONAL_QUESTIONS" | "SUMMARY";
type TimePreset = "LAST_YEAR" | "LAST_5_YEARS" | "LAST_10_YEARS" | "SINCE_2000" | "ANY" | "CUSTOM";
type Access = { academic: boolean; policy: boolean };

// Fallback population examples (used if LLM generation fails)
const FALLBACK_POPULATION_EXAMPLES = [
  "General population",
  "Adults",
  "Children"
] as const;

// Fallback outcome examples (used if LLM generation fails)
const FALLBACK_OUTCOME_EXAMPLES = [
  "Social well-being",
  "Better health outcomes",
  "Improved outcomes"
] as const;


// Geography constants (reused from ChatInterface)
const SPECIAL_REGIONS = [
  'All',
  'UK',
  'All but UK',
  'OECD members',
  'Non-OECD members',
  'G20',
  'G7',
  'North America',
  'South and Central America',
  'Europe',
  'Nordics',
  'APAC',
  'Africa',
];

const COUNTRY_LIST = [
  'USA', 'Spain', 'Japan', 'Canada', 'Germany', 'Sweden', 'Australia', 'France', 'Brazil', 'Netherlands', 'Italy', 'Portugal', 'Peru', 'Mexico', 'Turkey', 'Austria', 'Singapore', 'China', 'Switzerland', 'Belgium', 'Philippines', 'South Africa', 'Ireland', 'Denmark', 'Taiwan', 'Uruguay', 'Colombia', 'Romania', 'Finland', 'Thailand', 'Norway', 'Czech Republic', 'Chile', 'Indonesia', 'New Zealand', 'India', 'Argentina', 'Tanzania', 'Latvia', 'Slovakia', 'Lithuania', 'Slovenia', 'Bulgaria', 'Iceland', 'Greece', 'Paraguay', 'Hungary', 'Luxembourg', 'Estonia', 'Ukraine', 'Morocco', 'Serbia', 'Trinidad and Tobago', 'Cyprus', 'Ecuador', 'Georgia', 'Moldova', 'South Korea', 'Sri Lanka', 'Malaysia', 'Uganda', 'Kosovo', 'North Macedonia', 'Lebanon', 'El Salvador', 'Honduras', 'Belarus', 'Micronesia', 'Russia', 'Panama', 'Israel', 'Kenya', 'Maldives', 'Iran', 'Bosnia and Herzegovina', 'Afghanistan', 'Egypt', 'Croatia', 'Barbados', 'Bolivia', 'Tunisia', 'Vietnam', 'Costa Rica', 'Mauritius', 'Oman', 'Jamaica', 'Nigeria', 'Montenegro', 'Bahamas', 'Iraq', 'Cambodia', 'Bangladesh', 'Azerbaijan', 'Nepal', 'Ghana', 'Mongolia', 'Timor Leste', 'Bhutan', 'Cameroon', 'Brunei', 'Liberia', 'Saudi Arabia', 'Ethiopia', 'Pakistan', 'Papua New Guinea', 'Venezuela', 'Namibia', 'Albania', 'Guyana', 'Syria', 'Nicaragua', 'Kyrgyzstan', 'Malta', 'Haiti', 'Cape Verde', 'Samoa', 'Uzbekistan', 'Qatar', 'Myanmar', 'Benin', 'Mauritania', 'Mozambique', 'Algeria', 'Zambia', 'Solomon Islands', 'Kiribati', 'Kuwait', 'Armenia', 'Jordan', 'Burkina Faso', 'Andorra', 'Palau', 'Botswana', 'Mali', 'Bahrain', 'Rwanda', 'Senegal', 'Belize', 'United Arab Emirates', 'Fiji', 'Vanuatu', 'Libya', 'Suriname', 'Cuba', 'Laos', 'Togo', 'Tonga', 'Eswatini', 'Angola', 'Tajikistan', 'Ivory Coast', 'Guinea', 'Zimbabwe', 'Malawi', 'Marshall Islands', 'Burundi', 'Niger', 'Madagascar', 'Sudan', 'Somalia', 'Turkmenistan', 'Tuvalu', 'Seychelles', 'South Sudan', 'Sao Tome and Principe', 'Central African Republic', 'Sierra Leone', 'Yemen', 'Democratic Republic Of The Congo', 'San Marino', 'Chad', 'Palestine', 'Vatican City', 'Nauru', 'Kazakhstan', 'Equatorial Guinea', 'Lesotho', 'Monaco', 'North Korea', 'Saint Kitts and Nevis', 'Liechtenstein', 'Djibouti', 'Comoros', 'Gambia', 'Gabon', 'Eritrea', 'Guinea-Bissau'
];

const COUNTRIES = [
  "UK",
  "Europe",
  "OECD"
];

// Search context type - stores all the structured data
export type SearchContext = {
  researchQuestion: string;
  population: {
    selected: string[]; // Selected population options (examples + custom)
    keepBroad: boolean; // "Keep it broad" option
  };
  outcome: {
    selected: string[]; // Selected outcome options (examples + custom)
    keepBroad: boolean; // "Keep it broad" option
  };
  parameters: {
    sources: ("openalex" | "overton")[];
    access: Access;
    geography: string[];
    timePreset: TimePreset;
    customFrom?: string;
    customTo?: string;
  };
  screeningFactors: string[]; // Free text factors for screening
  additionalQuestions: string[]; // Additional research questions
  maxResults: number;
};

// ---------------- STATE ----------------
interface WizardState {
  step: Step;
  researchQuestion: string;
  population: { selected: string[]; keepBroad: boolean };
  outcome: { selected: string[]; keepBroad: boolean };
  generatedPopulationOptions: string[];
  generatedOutcomeOptions: string[];
  generatedAdditionalQuestions: string[];
  isGeneratingOptions: boolean;
  parameters: {
    sources: ("openalex" | "overton")[];
    access: Access;
    geography: string[];
    timePreset: TimePreset;
    customFrom?: string;
    customTo?: string;
  };
  screeningFactors: string[];
  additionalQuestions: string[];
  maxResults: number;
  set: (p: Partial<WizardState>) => void;
  next: () => void;
  back: () => void;
  buildContext: () => SearchContext;
}

export const useWizard = create<WizardState>((set, get) => ({
  step: "ASK",
  researchQuestion: "",
  population: { selected: [], keepBroad: false },
  outcome: { selected: [], keepBroad: false },
  generatedPopulationOptions: [],
  generatedOutcomeOptions: [],
  generatedAdditionalQuestions: [],
  isGeneratingOptions: false,
  parameters: {
    sources: [],
    access: { academic: true, policy: true },
    geography: [],
    timePreset: "LAST_10_YEARS",
    customFrom: undefined,
    customTo: undefined,
  },
  screeningFactors: [],
  additionalQuestions: [],
  maxResults: 30,
  set: (p) => set(p),
  next: () => {
    const s = get();
    // Skip ADDITIONAL_QUESTIONS step - go directly from SCREENING to SUMMARY
    const steps: Step[] = ["ASK", "POPULATION", "OUTCOME", "PARAMETERS", "SCREENING", "ADDITIONAL_QUESTIONS", "SUMMARY"];
    const currentIdx = steps.indexOf(s.step);
    if (currentIdx < steps.length - 1) {
      const nextStep = steps[currentIdx + 1];
      // Skip ADDITIONAL_QUESTIONS - go directly to SUMMARY
      if (nextStep === "ADDITIONAL_QUESTIONS") {
        set({ step: "SUMMARY" });
      } else {
        set({ step: nextStep });
      }
    }
  },
  back: () => {
    const s = get();
    // Skip ADDITIONAL_QUESTIONS step - go directly from SUMMARY to SCREENING
    const steps: Step[] = ["ASK", "POPULATION", "OUTCOME", "PARAMETERS", "SCREENING", "ADDITIONAL_QUESTIONS", "SUMMARY"];
    const currentIdx = steps.indexOf(s.step);
    if (currentIdx > 0) {
      const prevStep = steps[currentIdx - 1];
      // Skip ADDITIONAL_QUESTIONS - go directly to SCREENING
      if (prevStep === "ADDITIONAL_QUESTIONS") {
        set({ step: "SCREENING" });
      } else {
        set({ step: prevStep });
      }
    }
  },
  buildContext: () => {
    const s = get();
    return {
      researchQuestion: s.researchQuestion,
      population: s.population,
      outcome: s.outcome,
      parameters: s.parameters,
      screeningFactors: s.screeningFactors,
      additionalQuestions: s.additionalQuestions,
      maxResults: s.maxResults,
    };
  },
}));

// ---------------- HELPERS ----------------
function ProgressBar({ step }: { step: Step }) {
  // Skip ADDITIONAL_QUESTIONS in progress calculation
  const steps: Step[] = ["ASK", "POPULATION", "OUTCOME", "PARAMETERS", "SCREENING", "SUMMARY"];
  const currentIdx = steps.indexOf(step);
  const pct = Math.round(((currentIdx + 1) / steps.length) * 100);
  return (
    <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
      <div className="h-full bg-blue-600 transition-all" style={{ width: `${pct}%` }} />
    </div>
  );
}

function generateImpliedResearchQuestion(context: SearchContext): string {
  const parts: string[] = [];
  
  // Start with base question
  if (context.researchQuestion) {
    parts.push(context.researchQuestion);
  } else {
    parts.push("What interventions");
  }
  
  // Add population context
  if (context.population.selected.length > 0) {
    const popText = context.population.selected.length === 1 
      ? context.population.selected[0]
      : context.population.selected.join(", ");
    parts.push(`for ${popText}`);
  }
  
  // Add outcome context
  if (context.outcome.selected.length > 0) {
    const outcomeText = context.outcome.selected.length === 1
      ? context.outcome.selected[0]
      : context.outcome.selected.join(", ");
    parts.push(`could achieve ${outcomeText}`);
  }
  
  // If we have a base question, return it; otherwise construct from parts
  if (context.researchQuestion) {
    return context.researchQuestion;
  }
  
  return parts.join(" ") + "?";
}

// ---------------- SCREENS ----------------
function ScreenAsk() {
  const s = useWizard();
  const { generatePopulationOptions, generateOutcomeOptions } = useAPI();

  const handleNext = async () => {
    const researchQuestion = s.researchQuestion.trim();
    if (!researchQuestion) return;

    // Generate population and outcome options
    s.set({ isGeneratingOptions: true });
    
    try {
      // Generate both in parallel
      const [populationResponse, outcomeResponse] = await Promise.all([
        generatePopulationOptions(researchQuestion).catch(() => ({ population_options: [] })),
        generateOutcomeOptions(researchQuestion).catch(() => ({ outcome_options: [] })),
      ]);

      s.set({ 
        generatedPopulationOptions: populationResponse?.population_options || [],
        generatedOutcomeOptions: outcomeResponse?.outcome_options || [],
        step: "POPULATION"
      });
    } catch (error) {
      console.error('Failed to generate options:', error);
      // Continue with empty options if generation fails
      s.set({ 
        generatedPopulationOptions: [],
        generatedOutcomeOptions: [],
        step: "POPULATION" 
      });
    } finally {
      s.set({ isGeneratingOptions: false });
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 pt-32">
      <div className="text-center space-y-4">
        <div className="flex items-center justify-center gap-3">
          <h1 className="text-4xl font-bold tracking-tight">Find evidence on policy interventions</h1>
          <Tooltip content={
            <p className="max-w-xs">
              Alpha means this is an early prototype with limited functionality. 
              Features may be incomplete, unstable, or subject to change. 
              We&apos;re actively developing and improving the tool.
            </p>
          }>
            <Badge variant="default" className="text-sm bg-blue-600 hover:bg-blue-700 text-white font-semibold px-3 py-1 -mt-2">ALPHA</Badge>
          </Tooltip>
        </div>
      </div>

      <div className="space-y-6">
        <Textarea 
          autoFocus 
          placeholder="Example: Interventions to improve home learning environment for young children" 
          value={s.researchQuestion} 
          onChange={(e) => s.set({ researchQuestion: e.target.value })} 
        />
        <div className="flex justify-end">
          <Button 
            full 
            disabled={!s.researchQuestion.trim() || s.isGeneratingOptions} 
            onClick={handleNext}
          >
            {s.isGeneratingOptions ? 'Generating options...' : 'Continue'}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ScreenPopulation() {
  const s = useWizard();
  const [customInput, setCustomInput] = useState("");

  const togglePopulation = (pop: string) => {
    const current = s.population.selected;
    if (current.includes(pop)) {
      s.set({ population: { ...s.population, selected: current.filter(p => p !== pop) } });
    } else {
      s.set({ population: { ...s.population, selected: [...current, pop] } });
    }
  };

  const addCustom = () => {
    const trimmed = customInput.trim();
    // Use generated options or fallback to defaults
    const exampleOptions = s.generatedPopulationOptions.length > 0 
      ? [...s.generatedPopulationOptions, "Anyone"] as string[]
      : [...FALLBACK_POPULATION_EXAMPLES] as string[];
    if (trimmed && !s.population.selected.includes(trimmed) && !exampleOptions.includes(trimmed)) {
      s.set({ population: { ...s.population, selected: [...s.population.selected, trimmed] } });
      setCustomInput("");
    }
  };

  const removePopulation = (pop: string) => {
    s.set({ population: { ...s.population, selected: s.population.selected.filter(p => p !== pop) } });
  };

  // Use generated options or fallback to defaults
  const exampleOptions = s.generatedPopulationOptions.length > 0 
    ? [...s.generatedPopulationOptions, "Anyone"] as string[]
    : [...FALLBACK_POPULATION_EXAMPLES] as string[];
  const customOptions = s.population.selected.filter(pop => !exampleOptions.includes(pop));

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      {/* Navigation at top */}
      <div className="flex justify-between items-center">
        <Button variant="secondary" onClick={() => s.back()}>Back</Button>
        <Button onClick={() => s.next()}>Next</Button>
      </div>

      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Are you targeting a particular population?</h2>
        <p className="text-gray-600 text-lg">We will use this to filter only the most relevant information</p>
      </div>

      <div className="space-y-6 max-w-2xl mx-auto">
        {/* Options in single column */}
        <div className="flex flex-col gap-3">
          {exampleOptions.map((pop) => {
            const isSelected = s.population.selected.includes(pop);
            return (
              <button
                key={pop}
                type="button"
                onClick={() => togglePopulation(pop)}
                className={cx(
                  "w-full text-left px-4 py-4 rounded-xl transition ring-1 whitespace-normal break-words",
                  isSelected
                    ? "bg-blue-600 !text-white ring-blue-600"
                    : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
                )}
              >
                {pop}
              </button>
            );
          })}
          
          {/* Custom added options */}
          {customOptions.map((pop) => (
            <button
              key={pop}
              type="button"
              className="w-full text-left px-4 py-4 rounded-xl bg-blue-600 !text-white ring-1 ring-blue-600 flex items-center justify-between whitespace-normal break-words"
            >
              <span>{pop}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removePopulation(pop);
                }}
                className="ml-2 text-white hover:text-blue-100"
                aria-label="Remove"
              >
                ×
              </button>
            </button>
          ))}
        </div>

        {/* Custom input */}
        <div className="flex gap-3">
          <Input
            value={customInput}
            placeholder="Add your own population"
            onChange={(e) => setCustomInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addCustom()}
          />
          <Button onClick={addCustom}>+ Add</Button>
        </div>
      </div>
    </div>
  );
}

function ScreenOutcome() {
  const s = useWizard();
  const [customInput, setCustomInput] = useState("");

  const toggleOutcome = (outcome: string) => {
    const current = s.outcome.selected;
    if (current.includes(outcome)) {
      s.set({ outcome: { ...s.outcome, selected: current.filter(o => o !== outcome) } });
    } else {
      s.set({ outcome: { ...s.outcome, selected: [...current, outcome] } });
    }
  };

  const addCustom = () => {
    const trimmed = customInput.trim();
    // Use generated options or fallback to defaults
    const exampleOptions = s.generatedOutcomeOptions.length > 0
      ? [...s.generatedOutcomeOptions, "I don't have a particular outcome in mind"] as string[]
      : [...FALLBACK_OUTCOME_EXAMPLES, "I don't have a particular outcome in mind"] as string[];
    if (trimmed && !s.outcome.selected.includes(trimmed) && !exampleOptions.includes(trimmed)) {
      s.set({ outcome: { ...s.outcome, selected: [...s.outcome.selected, trimmed] } });
      setCustomInput("");
    }
  };

  const removeOutcome = (outcome: string) => {
    s.set({ outcome: { ...s.outcome, selected: s.outcome.selected.filter(o => o !== outcome) } });
  };

  // Use generated options or fallback to defaults
  const exampleOptions = s.generatedOutcomeOptions.length > 0
    ? [...s.generatedOutcomeOptions, "I don't have a particular outcome in mind"] as string[]
    : [...FALLBACK_OUTCOME_EXAMPLES, "I don't have a particular outcome in mind"] as string[];
  const customOptions = s.outcome.selected.filter(outcome => !exampleOptions.includes(outcome));

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      {/* Navigation at top */}
      <div className="flex justify-between items-center">
        <Button variant="secondary" onClick={() => s.back()}>Back</Button>
        <Button onClick={() => s.next()}>Next</Button>
      </div>

      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Are you interested in particular outcomes?</h2>
        <p className="text-gray-600 text-lg">We will use this to filter only the most relevant information</p>
      </div>

      <div className="space-y-6 max-w-2xl mx-auto">
        {/* Options in single column */}
        <div className="flex flex-col gap-3">
          {exampleOptions.map((outcome) => {
            const isSelected = s.outcome.selected.includes(outcome);
            return (
              <button
                key={outcome}
                type="button"
                onClick={() => toggleOutcome(outcome)}
                className={cx(
                  "w-full text-left px-4 py-4 rounded-xl transition ring-1 whitespace-normal break-words",
                  isSelected
                    ? "bg-blue-600 !text-white ring-blue-600"
                    : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
                )}
              >
                {outcome}
              </button>
            );
          })}
          
          {/* Custom added options */}
          {customOptions.map((outcome) => (
            <button
              key={outcome}
              type="button"
              className="w-full text-left px-4 py-4 rounded-xl bg-blue-600 !text-white ring-1 ring-blue-600 flex items-center justify-between whitespace-normal break-words"
            >
              <span>{outcome}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  removeOutcome(outcome);
                }}
                className="ml-2 text-white hover:text-blue-100"
                aria-label="Remove"
              >
                ×
              </button>
            </button>
          ))}
        </div>

        {/* Custom input */}
        <div className="flex gap-3">
          <Input
            value={customInput}
            placeholder="Add your own outcome"
            onChange={(e) => setCustomInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addCustom()}
          />
          <Button onClick={addCustom}>+ Add</Button>
        </div>
      </div>
    </div>
  );
}

function ScreenParameters() {
  const s = useWizard();
  const [selectedCountry, setSelectedCountry] = useState("");

  const toggleAccess = (k: keyof Access) => {
    s.set({ parameters: { ...s.parameters, access: { ...s.parameters.access, [k]: !s.parameters.access[k] } } });
  };

  const addGeo = (g: string) => {
    if (!s.parameters.geography.includes(g)) {
      s.set({ parameters: { ...s.parameters, geography: [...s.parameters.geography, g] } });
    }
  };

  const removeGeo = (g: string) => {
    s.set({ parameters: { ...s.parameters, geography: s.parameters.geography.filter(x => x !== g) } });
  };

  // Update sources based on access
  React.useEffect(() => {
    const sources: ("openalex" | "overton")[] = [];
    if (s.parameters.access.academic) sources.push("openalex");
    if (s.parameters.access.policy) sources.push("overton");
    s.set({ parameters: { ...s.parameters, sources } });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.parameters.access.academic, s.parameters.access.policy]);

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      {/* Navigation at top */}
      <div className="flex justify-between items-center">
        <Button variant="secondary" onClick={() => s.back()}>Back</Button>
        <Button onClick={() => s.next()}>Next</Button>
      </div>

      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Sources, geography and time window</h2>
        <p className="text-gray-600 text-lg">We will use this filter only the most relevant information</p>
      </div>

      <div className="space-y-8">
        {/* Sources */}
        <div className="space-y-4">
          <h3 className="font-semibold text-lg">Sources</h3>
          <div className="flex flex-wrap gap-3">
            <Chip active={s.parameters.access.academic} onClick={() => toggleAccess("academic")}>
              Academic (OpenAlex)
            </Chip>
            <Chip active={s.parameters.access.policy} onClick={() => toggleAccess("policy")}>
              Policy (think tanks and government)
            </Chip>
          </div>
        </div>

        {/* Time window */}
        <div className="space-y-4">
          <h3 className="font-semibold text-lg">Time window</h3>
          <div className="flex flex-wrap gap-3">
            {["LAST_YEAR", "LAST_5_YEARS", "LAST_10_YEARS", "SINCE_2000", "ANY", "CUSTOM"].map((p) => (
              <Chip
                key={p}
                active={s.parameters.timePreset === p}
                onClick={() => s.set({ parameters: { ...s.parameters, timePreset: p as TimePreset } })}
              >
                {p.replaceAll("_", " ")}
              </Chip>
            ))}
          </div>
          {s.parameters.timePreset === "CUSTOM" && (
            <div className="flex gap-3 max-w-lg">
              <div className="flex-1">
                <div className="text-xs text-gray-500 mb-2">From</div>
                <Input
                  type="date"
                  value={s.parameters.customFrom || ""}
                  onChange={(e) => s.set({ parameters: { ...s.parameters, customFrom: e.target.value } })}
                />
              </div>
              <div className="flex-1">
                <div className="text-xs text-gray-500 mb-2">To</div>
                <Input
                  type="date"
                  value={s.parameters.customTo || ""}
                  onChange={(e) => s.set({ parameters: { ...s.parameters, customTo: e.target.value } })}
                />
              </div>
            </div>
          )}
        </div>

        {/* Geography */}
        <div className="space-y-4 max-w-2xl">
          <h3 className="font-semibold text-lg">Geography</h3>
          {/* Separate quick options from custom added ones */}
          {(() => {
            const quickOptions = COUNTRIES;
            const customOptions = s.parameters.geography.filter(geo => !quickOptions.includes(geo));
            
            return (
              <div>
                {/* Quick options in single column */}
                <div className="flex flex-col gap-3">
                  {quickOptions.map((geo) => {
                    const isSelected = s.parameters.geography.includes(geo);
                    return (
                      <button
                        key={geo}
                        type="button"
                        onClick={() => {
                          if (isSelected) {
                            removeGeo(geo);
                          } else {
                            addGeo(geo);
                          }
                        }}
                        className={cx(
                          "w-full text-left px-4 py-4 rounded-xl transition ring-1 whitespace-normal break-words",
                          isSelected
                            ? "bg-blue-600 !text-white ring-blue-600"
                            : "bg-white text-gray-900 ring-gray-300 hover:bg-gray-50"
                        )}
                      >
                        {geo}
                      </button>
                    );
                  })}
                  
                  {/* Custom added options */}
                  {customOptions.map((geo) => (
                    <button
                      key={geo}
                      type="button"
                      className="w-full text-left px-4 py-4 rounded-xl bg-blue-600 !text-white ring-1 ring-blue-600 flex items-center justify-between whitespace-normal break-words"
                    >
                      <span>{geo}</span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          removeGeo(geo);
                        }}
                        className="ml-2 text-white hover:text-blue-100"
                        aria-label="Remove"
                      >
                        ×
                      </button>
                    </button>
                  ))}
                </div>
                
                {/* Custom input */}
                <div className="flex gap-3 mt-4">
                  <select
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-xl text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
                    value={selectedCountry}
                    onChange={(e) => setSelectedCountry(e.target.value)}
                  >
                    <option value="">Select a country or region</option>
                    <optgroup label="Regions & Groups">
                      {SPECIAL_REGIONS.map((region) => (
                        <option key={region} value={region}>{region}</option>
                      ))}
                    </optgroup>
                    <optgroup label="Countries">
                      {COUNTRY_LIST.sort().map((country) => (
                        <option key={country} value={country}>{country}</option>
                      ))}
                    </optgroup>
                  </select>
                  <Button onClick={() => { if (selectedCountry && !s.parameters.geography.includes(selectedCountry)) { addGeo(selectedCountry); setSelectedCountry(""); } }}>
                    + Add
                  </Button>
                </div>
              </div>
            );
          })()}
        </div>
      </div>
    </div>
  );
}

function ScreenScreening() {
  const s = useWizard();
  const [customInput, setCustomInput] = useState("");

  const addFactor = () => {
    if (customInput.trim() && !s.screeningFactors.includes(customInput.trim())) {
      s.set({ screeningFactors: [...s.screeningFactors, customInput.trim()] });
      setCustomInput("");
    }
  };

  const removeFactor = (factor: string) => {
    s.set({ screeningFactors: s.screeningFactors.filter(f => f !== factor) });
  };

  const handleNext = async () => {
    // Skip ADDITIONAL_QUESTIONS step - go directly to SUMMARY
    // (Keeping generation code commented out for future use)
    // s.set({ isGeneratingOptions: true });
    // 
    // try {
    //   const response = await generateAdditionalQuestions(
    //     s.researchQuestion,
    //     s.population.selected,
    //     s.outcome.selected
    //   ).catch(() => ({ additional_questions: [] }));
    //
    //   const generatedQuestions = response?.additional_questions || [];
    //   
    //   // Preselect generated questions
    //   s.set({ 
    //     generatedAdditionalQuestions: generatedQuestions,
    //     additionalQuestions: generatedQuestions,
    //     step: "ADDITIONAL_QUESTIONS"
    //   });
    // } catch (error) {
    //   console.error('Failed to generate additional questions:', error);
    //   // Continue with empty questions if generation fails
    //   s.set({ 
    //     generatedAdditionalQuestions: [],
    //     step: "ADDITIONAL_QUESTIONS" 
    //   });
    // } finally {
    //   s.set({ isGeneratingOptions: false });
    // }
    
    // Go directly to SUMMARY
    s.set({ step: "SUMMARY" });
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      {/* Navigation at top */}
      <div className="flex justify-between items-center">
        <Button variant="secondary" onClick={() => s.back()}>Back</Button>
        <Button onClick={handleNext} disabled={s.isGeneratingOptions}>
          {s.isGeneratingOptions ? "Generating..." : "Next"}
        </Button>
      </div>

      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Anything else to consider when screening the evidence?</h2>
        <p className="text-gray-600 text-lg">We will use this to filter only the most relevant information</p>
      </div>

      <div className="space-y-6 max-w-2xl mx-auto">
        {/* Selected factors as buttons */}
        {s.screeningFactors.length > 0 && (
          <div>
            {s.screeningFactors.map((factor) => (
              <button
                key={factor}
                type="button"
                className="w-full text-left px-4 py-4 rounded-xl bg-blue-600 !text-white ring-1 ring-blue-600 flex items-center justify-between mb-3"
              >
                <span>{factor}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFactor(factor);
                  }}
                  className="ml-2 text-white hover:text-blue-100"
                  aria-label="Remove"
                >
                  ×
                </button>
              </button>
            ))}
          </div>
        )}

        {/* Custom input */}
        <div className="flex gap-3">
          <Input
            value={customInput}
            placeholder="Add a screening factor (e.g., 'Only peer-reviewed studies', 'Focus on cost-effectiveness')"
            onChange={(e) => setCustomInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addFactor()}
          />
          <Button onClick={addFactor}>+ Add</Button>
        </div>
      </div>
    </div>
  );
}

function ScreenAdditionalQuestions() {
  const s = useWizard();
  const [customQuestion, setCustomQuestion] = useState("");

  const addQuestion = () => {
    if (customQuestion.trim() && !s.additionalQuestions.includes(customQuestion.trim())) {
      s.set({ additionalQuestions: [...s.additionalQuestions, customQuestion.trim()] });
      setCustomQuestion("");
    }
  };

  const removeQuestion = (q: string) => {
    s.set({ additionalQuestions: s.additionalQuestions.filter(x => x !== q) });
  };

  const toggleQuestion = (q: string) => {
    if (s.additionalQuestions.includes(q)) {
      removeQuestion(q);
    } else {
      s.set({ additionalQuestions: [...s.additionalQuestions, q] });
    }
  };

  // Combine generated and any custom questions that aren't already selected
  const allAvailableQuestions = [
    ...s.generatedAdditionalQuestions,
    ...s.additionalQuestions.filter((q: string) => !s.generatedAdditionalQuestions.includes(q))
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      {/* Navigation at top */}
      <div className="flex justify-between items-center">
        <Button variant="secondary" onClick={() => s.back()}>Back</Button>
        <Button onClick={() => s.next()}>Next</Button>
      </div>

      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Specific research questions?</h2>
        <p className="text-gray-600 text-lg">We will use these to shape the summary write-up</p>
      </div>

      <div className="space-y-6 max-w-2xl mx-auto">
        {/* Generated and selected questions as buttons */}
        {allAvailableQuestions.length > 0 && (
          <div>
            {allAvailableQuestions.map((q) => {
              const isSelected = s.additionalQuestions.includes(q);
              return (
                <button
                  key={q}
                  type="button"
                  onClick={() => toggleQuestion(q)}
                  className={cx(
                    "w-full text-left px-4 py-4 rounded-xl flex items-center justify-between mb-3",
                    isSelected
                      ? "bg-blue-600 !text-white ring-1 ring-blue-600"
                      : "bg-white text-gray-900 ring-1 ring-gray-300 hover:bg-gray-50"
                  )}
                >
                  <span>{q}</span>
                  {isSelected && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removeQuestion(q);
                      }}
                      className="ml-2 text-white hover:text-blue-100"
                      aria-label="Remove"
                    >
                      ×
                    </button>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Custom question input */}
        <div className="flex gap-3">
          <Input
            value={customQuestion}
            placeholder="Add your own question"
            onChange={(e) => setCustomQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addQuestion()}
          />
          <Button onClick={addQuestion}>+ Add</Button>
        </div>
      </div>
    </div>
  );
}

function ScreenSummary({ onRunAnalysis, isRunning = false }: { onRunAnalysis: (context: SearchContext) => void; isRunning?: boolean }) {
  const s = useWizard();
  const context = s.buildContext();
  const impliedQuestion = generateImpliedResearchQuestion(context);

  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 py-16">
      {/* Navigation at top */}
      <div className="flex justify-between items-center">
        <Button variant="secondary" onClick={() => s.back()} disabled={isRunning}>Back</Button>
        <Button onClick={() => onRunAnalysis(context)} disabled={isRunning}>
          {isRunning ? 'Starting up...' : 'Run Analysis'}
        </Button>
      </div>

      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold">Summary</h2>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Your research question</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-lg text-gray-800">{impliedQuestion}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Search parameters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <span className="font-medium">Population: </span>
            {context.population.selected.length > 0 ? (
              <span>{context.population.selected.join(", ")}</span>
            ) : (
              <span className="text-gray-500">Not specified</span>
            )}
          </div>
          <div>
            <span className="font-medium">Outcome: </span>
            {context.outcome.selected.length > 0 ? (
              <span>{context.outcome.selected.join(", ")}</span>
            ) : (
              <span className="text-gray-500">Not specified</span>
            )}
          </div>
          <div>
            <span className="font-medium">Sources: </span>
            <span>{context.parameters.sources.join(", ")}</span>
          </div>
          {context.parameters.geography.length > 0 && (
            <div>
              <span className="font-medium">Geography: </span>
              <span>{context.parameters.geography.join(", ")}</span>
            </div>
          )}
          <div>
            <span className="font-medium">Time window: </span>
            <span>{context.parameters.timePreset.replaceAll("_", " ")}</span>
          </div>
          {context.screeningFactors.length > 0 && (
            <div>
              <span className="font-medium">Screening factors: </span>
              <span>{context.screeningFactors.join(", ")}</span>
            </div>
          )}
          <div>
            <span className="font-medium">Max results: </span>
            <div className="inline-flex items-center gap-2 mt-1">
              <button
                type="button"
                className="px-2 py-1 rounded-lg ring-1 ring-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={() => s.set({ maxResults: Math.max(5, s.maxResults - 5) })}
                disabled={isRunning}
                aria-label="Decrease results"
              >–</button>
              <span className="min-w-[2ch] text-center">{s.maxResults}</span>
              <button
                type="button"
                className="px-2 py-1 rounded-lg ring-1 ring-gray-300 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                onClick={() => s.set({ maxResults: Math.min(200, s.maxResults + 5) })}
                disabled={isRunning}
                aria-label="Increase results"
              >+</button>
            </div>
          </div>
          {/* Additional questions step is currently skipped */}
          {/* {context.additionalQuestions.length > 0 && (
            <div>
              <span className="font-medium">Questions: </span>
              <ul className="list-disc pl-6 mt-2 space-y-1">
                {context.additionalQuestions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          )} */}
        </CardContent>
      </Card>
    </div>
  );
}


// ---------------- ROOT ----------------
interface SearchWizardProps {
  onRunAnalysis: (context: SearchContext) => void;
  isRunning?: boolean;
}

export default function SearchWizard({ onRunAnalysis, isRunning = false }: SearchWizardProps) {
  const s = useWizard();

  return (
    <div className="min-h-screen bg-white text-gray-900">
      <ProgressBar step={s.step} />
      {s.step === "ASK" && <ScreenAsk />}
      {s.step === "POPULATION" && <ScreenPopulation />}
      {s.step === "OUTCOME" && <ScreenOutcome />}
      {s.step === "PARAMETERS" && <ScreenParameters />}
      {s.step === "SCREENING" && <ScreenScreening />}
      {s.step === "ADDITIONAL_QUESTIONS" && <ScreenAdditionalQuestions />}
      {s.step === "SUMMARY" && <ScreenSummary onRunAnalysis={onRunAnalysis} isRunning={isRunning} />}
    </div>
  );
}
