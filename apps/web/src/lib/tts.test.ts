import { describe, expect, it } from 'vitest';
import { sentenceChunks, speechLang } from './tts';

describe('speechLang', () => {
  it('reads Devanagari with a Hindi voice and everything else in English', () => {
    expect(speechLang('नल')).toBe('hi-IN');
    expect(speechLang('रानी के घर में कौन सा जानवर है?')).toBe('hi-IN');
    expect(speechLang('Say the sound of this letter.')).toBe('en-IN');
    expect(speechLang('Touch 47')).toBe('en-IN');
    expect(speechLang('')).toBe('en-IN');
  });
});

describe('sentenceChunks', () => {
  it('splits on danda and Latin sentence ends', () => {
    expect(sentenceChunks('मेरा नाम रानी है। Hello there. Bye!')).toEqual(['मेरा नाम रानी है।', 'Hello there.', 'Bye!']);
  });
});
