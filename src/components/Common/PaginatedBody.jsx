import { Children } from 'react';
import usePagination from '../../hooks/usePagination';
import Pagination from './Pagination';
// Slice rendered rows only; callers retain complete data for saves and exports.
export default function PaginatedBody({children,resetKey,pageSize=10, ...props}) {
 const rows=Children.toArray(children);
 const paging=usePagination(rows,resetKey,pageSize);
 return <tbody {...props}>{paging.items}{paging.pageCount>1&&<tr><td colSpan={100}><Pagination {...paging} label="loaded records"/></td></tr>}</tbody>;
}
