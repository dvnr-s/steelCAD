import { describe, it, expect } from 'vitest'
import { listLeafIds, makeEmptyTree } from './editorStore'

const leaf = (id) => ({ id, isLeaf: true, width: 2, height: 2 })
const branch = (id, children) => ({
  id, isLeaf: false, width: 4, height: 2,
  split: { id: `${id}-split`, direction: 'vertical', position: 0.5, children },
})

const tree = (root) => ({ frame: { width: 4, height: 3, rootRegion: root } })

describe('listLeafIds', () => {
  it('returns the single root leaf', () => {
    expect(listLeafIds(tree(leaf('a')))).toEqual(['a'])
  })

  it('walks splits depth-first (reading order)', () => {
    const root = branch('root', [
      branch('left', [leaf('a'), leaf('b')]),
      leaf('c'),
    ])
    expect(listLeafIds(tree(root))).toEqual(['a', 'b', 'c'])
  })

  it('treats a branch without a split as a leaf (defensive)', () => {
    const weird = { id: 'w', isLeaf: false, width: 2, height: 2, split: null }
    expect(listLeafIds(tree(weird))).toEqual(['w'])
  })

  it('handles empty / missing trees', () => {
    expect(listLeafIds(null)).toEqual([])
    expect(listLeafIds({})).toEqual([])
  })

  it('finds the root region of a fresh editor tree', () => {
    const t = makeEmptyTree('T', 5, 4)
    expect(listLeafIds(t)).toEqual([t.frame.rootRegion.id])
  })
})
