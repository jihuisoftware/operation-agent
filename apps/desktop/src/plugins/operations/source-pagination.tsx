import { Button, Input } from '@hermes/plugin-sdk'
import { useState } from 'react'

interface SourcePaginationProps {
  page: number
  totalPages: number
  onPageChange: (page: number) => void
}

export function SourcePagination({ page, totalPages, onPageChange }: SourcePaginationProps) {
  const [target, setTarget] = useState(String(page))
  const value = Number(target)
  const valid = target.trim() !== '' && Number.isInteger(value) && value >= 1 && value <= totalPages

  return (
    <nav aria-label="来源素材分页" className="flex flex-wrap items-center gap-3 pb-6">
      <Button disabled={page <= 1} onClick={() => onPageChange(1)} variant="outline">
        首页
      </Button>
      <Button disabled={page <= 1} onClick={() => onPageChange(page - 1)} variant="outline">
        上一页
      </Button>
      <span className="text-sm">
        第 {page} 页 / 共 {totalPages} 页
      </span>
      <Button disabled={page >= totalPages} onClick={() => onPageChange(page + 1)} variant="outline">
        下一页
      </Button>
      <Button disabled={page >= totalPages} onClick={() => onPageChange(totalPages)} variant="outline">
        末页
      </Button>
      <form
        className="flex items-center gap-2"
        onSubmit={event => {
          event.preventDefault()

          if (valid) {
            onPageChange(value)
          }
        }}
      >
        <label className="text-sm" htmlFor="source-page-number">
          跳至
        </label>
        <Input
          aria-label="跳转页码"
          className="w-20"
          id="source-page-number"
          max={totalPages}
          min={1}
          onChange={event => setTarget(event.target.value)}
          required
          step={1}
          type="number"
          value={target}
        />
        <span className="text-sm">页</span>
        <Button disabled={!valid || value === page} type="submit" variant="outline">
          跳转
        </Button>
      </form>
    </nav>
  )
}
