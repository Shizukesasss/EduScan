import { useState } from 'react';
import { paginate } from '../services/pagination';
export default function usePagination(items, resetKey='', pageSize=10) {
 const [state,setState]=useState({key:resetKey,page:1});
 const result=paginate(items,state.key===resetKey?state.page:1,pageSize);
 if(state.key!==resetKey || state.page!==result.page) setState({key:resetKey,page:result.page});
 return {...result,setPage:page=>setState({key:resetKey,page})};
}
