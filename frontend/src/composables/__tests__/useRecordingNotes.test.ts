import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import type { TranscriptLine } from '@/composables/useWebSocket'

vi.mock('@/api/notes', () => ({ saveNotes: vi.fn().mockResolvedValue(undefined) }))

import { useRecordingNotes } from '../useRecordingNotes'

describe('useRecordingNotes 连续随记', () => {
  it('同一行多条随记全部保留，可按 id 编辑与删除', () => {
    const wsLines = ref([{ speaker_id: 0, speaker_name: 'A', text: 'x', isFinal: true, begin_time: 1000 } as TranscriptLine])
    const notes = useRecordingNotes(wsLines, ref(0), ref('t1'))
    notes.addNote('一')
    notes.addNote('二')
    notes.addNote('三')
    expect(notes.notesByLine.value[0].map(n => n.text)).toEqual(['一', '二', '三'])
    expect(notes.noteCount.value).toBe(3)

    const mid = notes.notesByLine.value[0][1].id
    notes.updateNote(mid, '二改')
    expect(notes.notesByLine.value[0].map(n => n.text)).toEqual(['一', '二改', '三'])

    notes.deleteNote(mid)
    expect(notes.notesByLine.value[0].map(n => n.text)).toEqual(['一', '三'])
  })
})
